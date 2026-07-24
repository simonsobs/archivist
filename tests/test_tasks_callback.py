# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Integration tests for archivist.tasks.callback.process_callbacks."""

import datetime
import unittest
import unittest.mock

import pytest
import requests
from conftest import make_archive_item

from archivist.orm.archive import Archive
from archivist.settings import LibrarianCallbackConfig
from archivist.tasks.callback import process_callbacks

LIBRARIAN = "test-librarian"


@pytest.mark.usefixtures("db_session")
class TestProcessCallbacksBase(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _inject(self, db_session, use_settings, archive_root, monkeypatch):
        self.session = db_session
        self.settings = use_settings
        self.archive_root = archive_root
        self.settings.librarians = {LIBRARIAN: LibrarianCallbackConfig(url="https://librarian.example.org")}
        # get_settings() reloads from the config file on each call, so pin the
        # callback task to this in-memory Settings (which carries `librarians`).
        monkeypatch.setattr("archivist.tasks.callback.get_settings", lambda: self.settings)

    def _completed_archive(
        self,
        manifest_id="m1",
        *,
        librarian_name=LIBRARIAN,
        callback_state="pending",
        callback_attempts=0,
        callback_next_retry=None,
        completed=True,
        failed=False,
        completed_time=None,
    ):
        """Persist an archive row in the state the callback loop expects."""

        item = make_archive_item(
            self.session,
            manifest_id=manifest_id,
            librarian_name=librarian_name,
            archive_root=str(self.archive_root),
        )
        item.completed = completed
        item.failed = failed
        item.completed_time = completed_time or datetime.datetime.now(datetime.timezone.utc)
        item.archive_path = str(self.archive_root)
        item.librarian_archive_id = item.id
        item.callback_state = callback_state
        item.callback_attempts = callback_attempts
        item.callback_next_retry = callback_next_retry
        self.session.commit()
        return item

    def _reload(self, manifest_id="m1") -> Archive:
        self.session.expire_all()
        return self.session.query(Archive).filter_by(manifest_id=manifest_id).one()


class TestNothingDue(TestProcessCallbacksBase):
    def test_returns_false_when_no_rows_at_all(self):
        self.assertFalse(process_callbacks())

    def test_ignores_incomplete_archive(self):
        self._completed_archive(completed=False)

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()

    def test_ignores_failed_archive(self):
        self._completed_archive(failed=True)

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()

    def test_ignores_skipped_cli_archive(self):
        self._completed_archive(librarian_name="__cli__", callback_state="skipped")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()
        self.assertEqual(self._reload().callback_state, "skipped")

    def test_ignores_already_sent_archive(self):
        self._completed_archive(callback_state="sent")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()

    def test_ignores_exhausted_archive(self):
        self._completed_archive(callback_state="exhausted")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()

    def test_ignores_row_whose_backoff_has_not_elapsed(self):
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        self._completed_archive(callback_state="failed", callback_attempts=1, callback_next_retry=future)

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertFalse(process_callbacks())

        mock_send.assert_not_called()


class TestSuccessfulDelivery(TestProcessCallbacksBase):
    def test_marks_row_sent_and_reports_work_done(self):
        self._completed_archive()

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertTrue(process_callbacks())

        mock_send.assert_called_once()
        item = self._reload()
        self.assertEqual(item.callback_state, "sent")
        self.assertEqual(item.callback_attempts, 1)
        self.assertIsNone(item.callback_last_error)
        self.assertIsNotNone(item.callback_last_attempt)

    def test_sends_manifest_id_with_configured_endpoint_and_timeout(self):
        self._completed_archive(manifest_id="manifest-42")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            process_callbacks()

        args, kwargs = mock_send.call_args
        self.assertEqual(args[0].url, "https://librarian.example.org")
        self.assertEqual(kwargs["manifest_id"], "manifest-42")
        self.assertEqual(kwargs["timeout"], self.settings.callback_timeout_seconds)

    def test_clears_a_previous_error_on_success(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        item = self._completed_archive(callback_state="failed", callback_attempts=2, callback_next_retry=past)
        item.callback_last_error = "earlier boom"
        self.session.commit()

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback"):
            process_callbacks()

        item = self._reload()
        self.assertEqual(item.callback_state, "sent")
        self.assertEqual(item.callback_attempts, 3)
        self.assertIsNone(item.callback_last_error)

    def test_row_with_null_next_retry_is_due(self):
        self._completed_archive(callback_next_retry=None)

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertTrue(process_callbacks())

        mock_send.assert_called_once()

    def test_handles_one_row_per_call_oldest_first(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self._completed_archive("newer", completed_time=now)
        self._completed_archive("older", completed_time=now - datetime.timedelta(hours=1))

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertTrue(process_callbacks())

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["manifest_id"], "older")
        self.assertEqual(self._reload("newer").callback_state, "pending")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertTrue(process_callbacks())

        self.assertEqual(mock_send.call_args.kwargs["manifest_id"], "newer")


class TestFailedDelivery(TestProcessCallbacksBase):
    def test_post_error_schedules_a_backoff_retry(self):
        self._completed_archive()

        with unittest.mock.patch(
            "archivist.tasks.callback.send_archive_callback",
            side_effect=requests.exceptions.ConnectionError("no route"),
        ):
            self.assertTrue(process_callbacks())

        item = self._reload()
        self.assertEqual(item.callback_state, "failed")
        self.assertEqual(item.callback_attempts, 1)
        self.assertIn("no route", item.callback_last_error)
        # First retry waits one base interval (base * 2 ** 0).
        self.assertEqual(
            item.callback_next_retry - item.callback_last_attempt,
            datetime.timedelta(seconds=self.settings.callback_retry_base_seconds),
        )

    def test_backoff_grows_exponentially_with_attempts(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        self._completed_archive(callback_state="failed", callback_attempts=2, callback_next_retry=past)

        with unittest.mock.patch(
            "archivist.tasks.callback.send_archive_callback",
            side_effect=RuntimeError("boom"),
        ):
            process_callbacks()

        item = self._reload()
        self.assertEqual(item.callback_attempts, 3)
        # Third attempt -> base * 2 ** 2.
        self.assertEqual(
            item.callback_next_retry - item.callback_last_attempt,
            datetime.timedelta(seconds=self.settings.callback_retry_base_seconds * 4),
        )

    def test_exhausts_at_the_attempt_cap(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        self._completed_archive(
            callback_state="failed",
            callback_attempts=self.settings.callback_max_attempts - 1,
            callback_next_retry=past,
        )

        with unittest.mock.patch(
            "archivist.tasks.callback.send_archive_callback",
            side_effect=RuntimeError("boom"),
        ):
            self.assertTrue(process_callbacks())

        item = self._reload()
        self.assertEqual(item.callback_state, "exhausted")
        self.assertEqual(item.callback_attempts, self.settings.callback_max_attempts)
        self.assertIn("boom", item.callback_last_error)

    def test_exhausted_row_is_not_retried_again(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        self._completed_archive(
            callback_state="failed",
            callback_attempts=self.settings.callback_max_attempts - 1,
            callback_next_retry=past,
        )

        with unittest.mock.patch(
            "archivist.tasks.callback.send_archive_callback",
            side_effect=RuntimeError("boom"),
        ) as mock_send:
            process_callbacks()
            self.assertFalse(process_callbacks())

        mock_send.assert_called_once()

    def test_unconfigured_librarian_takes_the_failure_path(self):
        self._completed_archive(librarian_name="unknown-librarian")

        with unittest.mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
            self.assertTrue(process_callbacks())

        mock_send.assert_not_called()
        item = self._reload()
        self.assertEqual(item.callback_state, "failed")
        self.assertEqual(item.callback_attempts, 1)
        self.assertIn("no endpoint configured", item.callback_last_error)
        self.assertIn("unknown-librarian", item.callback_last_error)

    def test_long_error_is_truncated_to_the_column_width(self):
        self._completed_archive()

        with unittest.mock.patch(
            "archivist.tasks.callback.send_archive_callback",
            side_effect=RuntimeError("x" * 5000),
        ):
            process_callbacks()

        self.assertEqual(len(self._reload().callback_last_error), 1024)


if __name__ == "__main__":
    unittest.main()
