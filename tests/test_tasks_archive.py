# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Integration tests for archivist.tasks.archive (start_archive, process_status_queue)."""

import queue as stdlib_queue
import time
import unittest
import unittest.mock

import pytest
from conftest import make_archive_item, make_manifest_entry

from archivist.orm.archive import Archive
from archivist.queue import get_status_queue
from archivist.storage.storage_disk import StorageDisk
from archivist.tasks.archive import (
    process_status_queue,
    reconcile_orphaned_archives,
    start_archive,
)


@pytest.mark.usefixtures("db_session")
class TestTasksArchiveBase(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _inject(self, db_session, use_settings, local_root, archive_root):
        self.session = db_session
        self.settings = use_settings
        self.local_root = local_root
        self.archive_root = archive_root

    def _enqueue_manifest_for(self, source_path, manifest_id="m1"):
        return make_archive_item(
            self.session,
            manifest_id=manifest_id,
            archive_root=str(self.archive_root),
            entries=[make_manifest_entry(instance_path=str(source_path))],
        )


class TestStartArchive(TestTasksArchiveBase):
    def test_start_archive_noop_when_queue_empty(self):
        start_archive(librarian_name="test-librarian")
        self.assertEqual(get_status_queue().size, 0)

    def test_start_archive_dequeues_and_enqueues_status(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        self._enqueue_manifest_for(source)

        start_archive(librarian_name="test-librarian")

        self.assertEqual(get_status_queue().size, 1)

        item = self.session.query(Archive).filter_by(manifest_id="m1").one()
        self.assertTrue(item.consumed)

    def test_start_archive_actually_copies_file(self):
        source = self.local_root / "file.txt"
        source.write_text("archived-content")
        self._enqueue_manifest_for(source)

        start_archive(librarian_name="test-librarian")

        task = get_status_queue().dequeue(block=False)
        task.future.result(timeout=5)

        dest = self.archive_root / "file.txt"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "archived-content")


class TestProcessStatusQueue(TestTasksArchiveBase):
    def test_process_status_queue_noop_when_empty(self):
        process_status_queue()

    def test_process_status_queue_completes_finished_task(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        self._enqueue_manifest_for(source)

        start_archive(librarian_name="test-librarian")

        deadline = time.time() + 5
        while time.time() < deadline:
            process_status_queue()
            self.session.expire_all()
            item = self.session.query(Archive).filter_by(manifest_id="m1").one()
            if item.completed:
                break
            time.sleep(0.05)

        self.assertTrue(item.completed)
        self.assertFalse(item.failed)

    def test_process_status_queue_requeues_unfinished_task(self):
        class _FakeFuture:
            def done(self):
                return False

        class _FakeStorageTask:
            def __init__(self):
                self.future = _FakeFuture()
                self._archive = type("A", (), {"manifest_id": "does-not-matter"})()

        status_queue = get_status_queue()
        status_queue.enqueue(_FakeStorageTask())

        process_status_queue()

        self.assertEqual(status_queue.size, 1)

    def test_process_status_queue_swallows_empty(self):
        with self.assertRaises(stdlib_queue.Empty):
            get_status_queue().dequeue(block=False)
        process_status_queue()

    def test_process_status_queue_returns_when_no_matching_db_row(self):
        class _FakeFuture:
            def done(self):
                return True

        class _FakeStorageTask:
            def __init__(self):
                self.future = _FakeFuture()
                self._archive = type("A", (), {"manifest_id": "no-such-manifest"})()

        status_queue = get_status_queue()
        status_queue.enqueue(_FakeStorageTask())

        # Should not raise, even though no ArchiveQueue row matches.
        process_status_queue()

        self.assertEqual(status_queue.size, 0)

    def test_process_status_queue_marks_item_failed_when_complete_raises(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        self._enqueue_manifest_for(source)

        start_archive(librarian_name="test-librarian")

        deadline = time.time() + 5
        task = get_status_queue().dequeue(block=False)
        while time.time() < deadline and not task.future.done():
            time.sleep(0.05)
        get_status_queue().enqueue(task)

        with unittest.mock.patch.object(Archive, "complete", side_effect=RuntimeError("boom")):
            process_status_queue()

        self.session.expire_all()
        item = self.session.query(Archive).filter_by(manifest_id="m1").one()
        self.assertTrue(item.completed)
        self.assertTrue(item.failed)

    def test_process_status_queue_sleeps_and_swallows_unexpected_exception(self):
        class _BoomStorageTask:
            @property
            def future(self):
                raise RuntimeError("boom")

        status_queue = get_status_queue()
        status_queue.enqueue(_BoomStorageTask())

        with unittest.mock.patch("archivist.tasks.archive.sleep") as mock_sleep:
            process_status_queue()

        mock_sleep.assert_called_once_with(1)


class TestReconcileOrphanedArchives(TestTasksArchiveBase):
    def _make_orphan(self, manifest_id, *, content="hello", size=None, retries=0):
        """Create a source file and a consumed-but-incomplete Archive row (an orphan)."""
        source = self.local_root / f"{manifest_id}.txt"
        source.write_text(content)
        if size is None:
            size = len(content)

        item = make_archive_item(
            self.session,
            manifest_id=manifest_id,
            archive_root=str(self.archive_root),
            entries=[make_manifest_entry(instance_path=str(source), size=size)],
        )
        item.consumed = True
        item.retries = retries
        self.session.commit()
        return item, source

    def _dest_for(self, source):
        return self.archive_root / source.relative_to(self.local_root)

    def test_completes_orphan_already_present_at_destination(self):
        item, source = self._make_orphan("verified", content="hello")
        dest = self._dest_for(source)
        dest.write_text("hello")  # 5 bytes, matches manifest size

        reconcile_orphaned_archives()

        self.session.expire_all()
        item = self.session.query(Archive).filter_by(manifest_id="verified").one()
        self.assertTrue(item.completed)
        self.assertFalse(item.failed)
        self.assertEqual(item.archive_path, str(self.archive_root))

    def test_requeues_orphan_not_present_and_under_retry_cap(self):
        self._make_orphan("requeue-me", content="hello", retries=0)
        # No destination file -> verify() is False.

        reconcile_orphaned_archives()

        self.session.expire_all()
        item = self.session.query(Archive).filter_by(manifest_id="requeue-me").one()
        self.assertFalse(item.consumed)
        self.assertIsNone(item.consumed_time)
        self.assertEqual(item.retries, 1)
        self.assertFalse(item.completed)

    def test_fails_orphan_at_or_over_retry_cap(self):
        cap = self.settings.max_archive_retries
        self._make_orphan("give-up", content="hello", retries=cap)
        # No destination file -> verify() is False, and retries == cap.

        reconcile_orphaned_archives()

        self.session.expire_all()
        item = self.session.query(Archive).filter_by(manifest_id="give-up").one()
        self.assertTrue(item.completed)
        self.assertTrue(item.failed)
        self.assertEqual(item.retries, cap)  # not requeued, so retries did not increment

    def test_leaves_non_orphan_rows_untouched(self):
        # A fresh, unconsumed row is not an orphan and must not be reconciled.
        make_archive_item(
            self.session,
            manifest_id="fresh",
            archive_root=str(self.archive_root),
        )

        reconcile_orphaned_archives()

        self.session.expire_all()
        item = self.session.query(Archive).filter_by(manifest_id="fresh").one()
        self.assertFalse(item.consumed)
        self.assertFalse(item.completed)

    def test_one_bad_orphan_does_not_abort_the_sweep(self):
        # First orphan is fine and should be requeued; second orphan's verify blows up.
        self._make_orphan("good", content="hello", retries=0)
        self._make_orphan("bad", content="hello", retries=0)

        real_verify = StorageDisk.verify

        def flaky_verify(self, archive):
            if archive.manifest_id == "bad":
                raise RuntimeError("boom")
            return real_verify(self, archive)

        with unittest.mock.patch.object(StorageDisk, "verify", flaky_verify):
            reconcile_orphaned_archives()

        self.session.expire_all()
        good = self.session.query(Archive).filter_by(manifest_id="good").one()
        self.assertEqual(good.retries, 1)  # good was still processed
        self.assertFalse(good.consumed)


if __name__ == "__main__":
    unittest.main()
