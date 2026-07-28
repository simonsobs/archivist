# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import queue as stdlib_queue
import time
from unittest import mock

import pytest
from conftest import make_archive_item, make_manifest_entry, make_orphan

from archivist.orm import Archive
from archivist.queue import Queue, get_status_queue
from archivist.tasks.archive import process_status_queue, reconcile_orphaned_archives, start_archive


class _FakeStorageTask:
    """Stands in for a storage backend's return value, without doing any I/O."""

    def __init__(self, done, manifest_id="m1"):
        self.future = mock.Mock(done=mock.Mock(return_value=done))
        self._archive = mock.Mock(manifest_id=manifest_id)


@pytest.fixture
def enqueue_manifest(db_session, archive_root):
    """Queue a real archive job for `source_path` and return its manifest id."""

    def _enqueue(source_path, manifest_id="m1"):
        make_archive_item(
            db_session,
            manifest_id=manifest_id,
            archive_root=str(archive_root),
            entries=[make_manifest_entry(instance_path=str(source_path))],
        )
        return manifest_id

    return _enqueue


def _drain_until_completed(session, manifest_id, timeout=5):
    """Poll the status worker until the queued row is closed out (or we give up)."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        process_status_queue()
        session.expire_all()
        item = session.query(Archive).filter_by(manifest_id=manifest_id).one()
        if item.completed:
            return item
        time.sleep(0.05)

    return item


def test_queue_is_fifo():
    q = Queue()
    assert q.size == 0

    q.enqueue("first")
    q.enqueue("second")
    assert q.size == 2
    assert [q.dequeue(), q.dequeue()] == ["first", "second"]
    q.task_done()

    with pytest.raises(stdlib_queue.Empty):
        q.dequeue(block=False)


def test_start_archive_takes_the_oldest_row_and_copies_its_files(
    db_session, enqueue_manifest, local_root, archive_root
):
    # An empty queue is the common case in the worker's busy-loop; it must be a no-op.
    start_archive(librarian_name="test-librarian")
    assert get_status_queue().size == 0

    source = local_root / "file.txt"
    source.write_text("archived-content")
    enqueue_manifest(source, manifest_id="older")
    time.sleep(0.01)
    enqueue_manifest(source, manifest_id="newer")

    start_archive(librarian_name="test-librarian")

    # One job per pass, oldest first: `newer` waits for the worker's next lap.
    assert db_session.query(Archive).filter_by(manifest_id="older").one().consumed
    assert not db_session.query(Archive).filter_by(manifest_id="newer").one().consumed

    task = get_status_queue().dequeue(block=False)
    task.future.result(timeout=5)
    assert (archive_root / "file.txt").read_text() == "archived-content"


def test_process_status_queue_marks_rows_completed_or_failed(db_session, enqueue_manifest, local_root, archive_root):
    """Either way the row must end up `completed`; `failed` is what distinguishes them."""

    source = local_root / "file.txt"
    source.write_text("hello")

    enqueue_manifest(source, manifest_id="stored-ok")
    start_archive(librarian_name="test-librarian")
    item = _drain_until_completed(db_session, "stored-ok")

    assert item.completed
    assert not item.failed
    # Where the data actually landed is recorded on the row, not just on disk.
    assert item.archive_path == str(archive_root)

    enqueue_manifest(source, manifest_id="storing-raised")
    start_archive(librarian_name="test-librarian")
    with mock.patch.object(Archive, "complete", side_effect=RuntimeError("boom")):
        item = _drain_until_completed(db_session, "storing-raised")

    assert item.completed
    assert item.failed


def test_process_status_queue_handles_tasks_it_cannot_close_out(db_session, use_settings):
    """
    The status worker busy-loops on this, so nothing here may raise: a task
    whose future is still running goes back on the queue, and one that can no
    longer be matched to a row (or is broken outright) is dropped.
    """

    status_queue = get_status_queue()

    status_queue.enqueue(_FakeStorageTask(done=False))
    process_status_queue()
    assert status_queue.size == 1
    status_queue.dequeue(block=False)

    status_queue.enqueue(_FakeStorageTask(done=True, manifest_id="no-such-manifest"))
    process_status_queue()
    assert status_queue.size == 0

    broken = mock.Mock()
    type(broken).future = mock.PropertyMock(side_effect=RuntimeError("boom"))
    status_queue.enqueue(broken)
    with mock.patch("archivist.tasks.archive.sleep"):  # skip the error path's back-off
        process_status_queue()
    assert status_queue.size == 0


def test_reconcile_orphaned_archives(db_session, use_settings, archive_root, local_root):
    """A crash leaves rows consumed-but-incomplete; startup has to close them out."""

    landed_archive = make_orphan(db_session, "landed", local_root, archive_root)
    orphan_file = archive_root / "landed.txt"
    orphan_file.write_text("content")

    nodest_archive = make_orphan(db_session, "nodest", local_root, archive_root)
    max_retries_archive = make_orphan(
        db_session, "max_retries", local_root, archive_root, retries=use_settings.max_archive_retries
    )

    reconcile_orphaned_archives()

    db_session.expire_all()

    assert landed_archive.completed and not landed_archive.failed
    assert landed_archive.archive_path == str(archive_root)
    assert landed_archive.retries == 0

    assert not nodest_archive.consumed
    assert nodest_archive.consumed_time is None
    assert nodest_archive.retries == 1
    assert not nodest_archive.completed

    assert max_retries_archive.failed
    assert max_retries_archive.retries == use_settings.max_archive_retries
