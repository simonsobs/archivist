# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.orm.archivequeue.ArchiveQueue, against a real sqlite DB."""

import unittest

import pytest

from archivist.orm.archivequeue import ArchiveQueue


@pytest.mark.usefixtures("db_session")
class TestArchiveQueueBase(unittest.TestCase):
    """Base TestCase that pulls the pytest `db_session` fixture into `self.session`."""

    @pytest.fixture(autouse=True)
    def _inject_session(self, db_session):
        self.session = db_session


class TestNewItem(TestArchiveQueueBase):
    def test_new_item_defaults(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=["/a"], root="/root")
        self.assertEqual(item.manifest_id, "m1")
        self.assertEqual(item.paths, ["/a"])
        self.assertEqual(item.root, "/root")
        self.assertEqual(item.retries, 0)
        self.assertFalse(item.consumed)
        self.assertFalse(item.completed)
        self.assertFalse(item.failed)

    def test_new_item_persists(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=["/a"], root="/root")
        self.session.add(item)
        self.session.commit()

        fetched = self.session.query(ArchiveQueue).filter_by(manifest_id="m1").one()
        self.assertEqual(fetched.root, "/root")

    def test_manifest_id_must_be_unique(self):
        from sqlalchemy.exc import IntegrityError

        self.session.add(ArchiveQueue.new_item(manifest_id="dup", manifest="{}", paths=[], root="/root"))
        self.session.commit()

        self.session.add(ArchiveQueue.new_item(manifest_id="dup", manifest="{}", paths=[], root="/root"))
        with self.assertRaises(IntegrityError):
            self.session.commit()


class TestDequeue(TestArchiveQueueBase):
    def test_dequeue_returns_none_when_empty(self):
        self.assertIsNone(ArchiveQueue.dequeue(self.session))

    def test_dequeue_marks_item_consumed(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=[], root="/root")
        self.session.add(item)
        self.session.commit()

        dequeued = ArchiveQueue.dequeue(self.session)

        self.assertEqual(dequeued.manifest_id, "m1")
        self.assertTrue(dequeued.consumed)
        self.assertIsNotNone(dequeued.consumed_time)

    def test_dequeue_returns_oldest_first(self):
        import time

        first = ArchiveQueue.new_item(manifest_id="first", manifest="{}", paths=[], root="/root")
        self.session.add(first)
        self.session.commit()

        time.sleep(0.01)

        second = ArchiveQueue.new_item(manifest_id="second", manifest="{}", paths=[], root="/root")
        self.session.add(second)
        self.session.commit()

        dequeued = ArchiveQueue.dequeue(self.session)

        self.assertEqual(dequeued.manifest_id, "first")

    def test_dequeue_skips_already_consumed_items(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=[], root="/root")
        self.session.add(item)
        self.session.commit()

        ArchiveQueue.dequeue(self.session)

        self.assertIsNone(ArchiveQueue.dequeue(self.session))


class TestCompleteAndFail(TestArchiveQueueBase):
    def test_complete_sets_flags(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=[], root="/root")
        self.session.add(item)
        self.session.commit()

        item.complete(self.session)

        self.assertTrue(item.completed)
        self.assertFalse(item.failed)
        self.assertIsNotNone(item.completed_time)

    def test_fail_sets_flags(self):
        item = ArchiveQueue.new_item(manifest_id="m1", manifest="{}", paths=[], root="/root")
        self.session.add(item)
        self.session.commit()

        item.fail(self.session)

        self.assertTrue(item.completed)
        self.assertTrue(item.failed)
        self.assertIsNotNone(item.completed_time)


if __name__ == "__main__":
    unittest.main()
