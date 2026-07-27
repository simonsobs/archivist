# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import time

from archivist.orm.archivequeue import ArchiveQueue


def test_dequeue_takes_the_oldest_unconsumed_item_and_marks_it_consumed(db_session):
    for manifest_id in ("first", "second"):
        db_session.add(ArchiveQueue.new_item(manifest_id=manifest_id, manifest="{}", paths=["/a"], root="/root"))
        db_session.commit()
        time.sleep(0.01)

    dequeued = ArchiveQueue.dequeue(db_session)

    assert dequeued.manifest_id == "first"
    assert dequeued.consumed
    assert dequeued.consumed_time is not None

    # Consumed items are never handed out again, and an empty queue is not an error.
    assert ArchiveQueue.dequeue(db_session).manifest_id == "second"
    assert ArchiveQueue.dequeue(db_session) is None
