# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.orm.archive.Archive, against a real sqlite DB."""

import unittest

import pytest
from conftest import make_archive_item

from archivist.orm import Archive, Manifest


@pytest.mark.usefixtures("db_session")
class TestArchiveQueueBase(unittest.TestCase):
    """Base TestCase that pulls the pytest `db_session` fixture into `self.session`."""

    @pytest.fixture(autouse=True)
    def _inject_session(self, db_session):
        self.session = db_session


class TestNewItem(TestArchiveQueueBase):
    def test_new_item_defaults(self):
        manifest = Manifest.get_or_create(self.session, manifest_id="m1", librarian_name="lib")
        item = Archive.new_item(manifest=manifest, archive_root="/root")
        self.assertIs(item.manifest, manifest)
        self.assertEqual(item.archive_root, "/root")
        self.assertEqual(item.retries, 0)
        self.assertFalse(item.consumed)
        self.assertFalse(item.completed)
        self.assertFalse(item.failed)

    def test_new_item_persists(self):
        make_archive_item(self.session, manifest_id="m1", archive_root="/root")

        fetched = self.session.query(Archive).filter_by(manifest_id="m1").one()
        self.assertEqual(fetched.archive_root, "/root")

    def test_manifest_id_must_be_unique(self):
        from sqlalchemy.exc import IntegrityError

        make_archive_item(self.session, manifest_id="dup", archive_root="/root")

        # A second archive job on the same manifest violates the unique FK (1:1).
        manifest = Manifest.get_or_create(self.session, manifest_id="dup", librarian_name="lib")
        self.session.add(Archive.new_item(manifest=manifest, archive_root="/root"))
        with self.assertRaises(IntegrityError):
            self.session.commit()


class TestDequeue(TestArchiveQueueBase):
    def test_dequeue_returns_none_when_empty(self):
        self.assertIsNone(Archive.dequeue(self.session))

    def test_dequeue_marks_item_consumed(self):
        make_archive_item(self.session, manifest_id="m1")

        dequeued = Archive.dequeue(self.session)

        self.assertEqual(dequeued.manifest_id, "m1")
        self.assertTrue(dequeued.consumed)
        self.assertIsNotNone(dequeued.consumed_time)

    def test_dequeue_returns_oldest_first(self):
        import time

        make_archive_item(self.session, manifest_id="first")
        time.sleep(0.01)
        make_archive_item(self.session, manifest_id="second")

        dequeued = Archive.dequeue(self.session)

        self.assertEqual(dequeued.manifest_id, "first")

    def test_dequeue_skips_already_consumed_items(self):
        make_archive_item(self.session, manifest_id="m1")

        Archive.dequeue(self.session)

        self.assertIsNone(Archive.dequeue(self.session))


class TestCompleteAndFail(TestArchiveQueueBase):
    def test_complete_sets_flags(self):
        item = make_archive_item(self.session, manifest_id="m1")

        item.complete(self.session)

        self.assertTrue(item.completed)
        self.assertFalse(item.failed)
        self.assertIsNotNone(item.completed_time)

    def test_fail_sets_flags(self):
        item = make_archive_item(self.session, manifest_id="m1")

        item.fail(self.session)

        self.assertTrue(item.completed)
        self.assertTrue(item.failed)
        self.assertIsNotNone(item.completed_time)


class TestRequeue(TestArchiveQueueBase):
    def test_requeue_resets_consumed_and_bumps_retries(self):
        item = make_archive_item(self.session, manifest_id="m1")
        Archive.dequeue(self.session)  # marks consumed=True, sets consumed_time
        self.assertTrue(item.consumed)

        item.requeue(self.session)

        self.assertFalse(item.consumed)
        self.assertIsNone(item.consumed_time)
        self.assertEqual(item.retries, 1)
        self.assertFalse(item.completed)

    def test_requeued_item_is_dequeueable_again(self):
        make_archive_item(self.session, manifest_id="m1")
        item = Archive.dequeue(self.session)
        self.assertIsNone(Archive.dequeue(self.session))  # consumed, not visible

        item.requeue(self.session)

        again = Archive.dequeue(self.session)
        self.assertIsNotNone(again)
        self.assertEqual(again.manifest_id, "m1")


if __name__ == "__main__":
    unittest.main()
