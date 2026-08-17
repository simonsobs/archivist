# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""
Tests for archivist.tasks.callback.

`process_callbacks` owns the delivery guarantee: which rows are due, what
happens when a POST fails, and when to give up. The POST itself is
`librarian_client.send_archive_callback` (tested separately) and is mocked
out here.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests
from conftest import LIBRARIAN_URL, make_awaiting_callback

from archivist.tasks.callback import process_callbacks


def _make_due_again(session, item):
    """Clear the backoff, as waiting out the retry interval would."""

    session.expire_all()
    item.callback_next_retry = None
    session.commit()


def test_reports_the_oldest_due_archive_and_marks_it_sent(db_session, use_settings, archive_root, send):
    """One callback per call, oldest first, so the worker loop stays responsive."""

    jan = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = make_awaiting_callback(db_session, archive_root, "older", completed_time=jan)
    newer = make_awaiting_callback(db_session, archive_root, "newer", completed_time=jan + timedelta(days=1))

    assert process_callbacks() is True

    assert send.call_args.args[0].url == LIBRARIAN_URL
    assert send.call_args.kwargs == {
        "manifest_id": "older",
        "archive_name": older.manifest.archive_name,
        "archive_id": "older",
        "archive_path": str(archive_root),
        "timeout": use_settings.callback_timeout_seconds,
    }

    db_session.expire_all()
    assert older.callback_state == "sent"
    assert older.callback_attempts == 1
    assert older.callback_last_error is None
    assert newer.callback_state == "pending"  # waits for the worker's next lap


@pytest.mark.parametrize(
    "overrides",
    [
        {"completed": False},
        {"failed": True},
        {"callback_state": "sent"},
        {"callback_state": "skipped"},
        {"callback_next_retry": datetime.now(timezone.utc) + timedelta(hours=1)},
    ],
    ids=["still-archiving", "archive-failed", "already-sent", "cli-job", "backoff-not-elapsed"],
)
def test_rows_that_are_not_due_are_left_alone(db_session, use_settings, archive_root, send, overrides):
    """Returning False is what lets the worker idle instead of spinning."""

    item = make_awaiting_callback(db_session, archive_root, **overrides)

    assert process_callbacks() is False

    send.assert_not_called()
    db_session.expire_all()
    assert item.callback_attempts == 0


def test_a_failed_delivery_backs_off_exponentially(db_session, use_settings, archive_root, send):
    """Backoff is measured from the attempt itself, and doubles per attempt."""

    base = use_settings.callback_retry_base_seconds
    send.side_effect = requests.exceptions.ConnectionError("no route")

    item = make_awaiting_callback(db_session, archive_root)

    assert process_callbacks() is True

    db_session.expire_all()
    assert item.callback_state == "errored"
    assert item.callback_attempts == 1
    assert "no route" in item.callback_last_error
    assert item.callback_next_retry - item.callback_last_attempt == timedelta(seconds=base)

    _make_due_again(db_session, item)
    assert process_callbacks() is True

    db_session.expire_all()
    assert item.callback_attempts == 2
    assert item.callback_next_retry - item.callback_last_attempt == timedelta(seconds=base * 2)


def test_gives_up_once_the_attempt_budget_is_spent(db_session, use_settings, archive_root, send):
    """An exhausted callback stops being retried; `resend-callback` is the only way back."""

    send.side_effect = requests.exceptions.ConnectionError("no route")

    item = make_awaiting_callback(db_session, archive_root)

    for _ in range(use_settings.callback_max_attempts):
        assert process_callbacks() is True
        _make_due_again(db_session, item)

    db_session.expire_all()
    assert item.callback_state == "failed"
    assert item.callback_attempts == use_settings.callback_max_attempts
    assert process_callbacks() is False


def test_an_unconfigured_librarian_is_treated_as_a_delivery_failure(db_session, use_settings, archive_root, send):
    """A misconfigured destination must not kill the worker; it retries like any other failure."""

    item = make_awaiting_callback(db_session, archive_root, librarian_name="unknown-librarian")

    assert process_callbacks() is True

    send.assert_not_called()
    db_session.expire_all()
    assert item.callback_state == "errored"
    assert "no endpoint configured" in item.callback_last_error
    assert item.callback_attempts == 1
