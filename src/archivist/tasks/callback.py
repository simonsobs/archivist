"""
The Librarian callback loop.

Once an archive job has completed successfully, Archivist owes the
originating Librarian a completion report. `process_callbacks` handles one
due callback per call (mirroring the one-item-per-call shape of
`process_status_queue`), so the worker loop stays responsive and one bad row
cannot stall the rest. Delivery state lives on the `Archive` row, so pending
retries survive a restart.
"""

import datetime
from typing import Callable

import loguru
from sqlalchemy import or_
from sqlalchemy.orm import Session

from archivist.core.librarian_client import send_archive_callback
from archivist.database import get_session
from archivist.orm.archive import Archive
from archivist.settings import get_settings


def process_callbacks(session_maker: Callable[[], Session] = get_session) -> bool:
    """
    Attempt the next due Librarian callback.

    Selects the oldest completed, non-failed archive whose callback is still
    owed (`pending`/`errored`) and whose backoff has elapsed, then POSTs the
    report. On success the row is marked `sent`; on failure it is marked
    `errored` with an exponential backoff, or `failed` once
    `callback_max_attempts` is reached. Returns ``True`` when an attempt was
    made and ``False`` when nothing was due, so the worker loop can back off
    instead of spinning.
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    session = session_maker()
    try:
        item = (
            session.query(Archive)
            .filter(
                Archive.completed.is_(True),
                Archive.failed.is_(False),
                Archive.callback_state.in_(("pending", "errored")),
                or_(
                    Archive.callback_next_retry.is_(None),
                    Archive.callback_next_retry <= now,
                ),
            )
            .order_by(Archive.completed_time.asc())
            .first()
        )
        if item is None:
            return False

        librarian_name = item.manifest.librarian_name
        if librarian_name == settings.cli_librarian_name:
            loguru.logger.info(f"Skipping callback for {item.id} to '{librarian_name}' (CLI librarian).")
            item.skip_callback()
            session.commit()
            return True
        config = settings.librarians.get(librarian_name)
        item.callback_attempts += 1
        item.callback_last_attempt = now
        try:
            if config is None:
                raise RuntimeError(f"no endpoint configured for librarian '{librarian_name}'")
            if item.archive_path is None:
                raise RuntimeError(f"archive {item.id} completed without an archive path")
            send_archive_callback(
                config,
                manifest_id=item.id,
                archive_name=item.manifest.archive_name,
                # Archivist's archive id is the manifest id; the Librarian
                # checks the two agree before recording anything.
                archive_id=item.id,
                archive_path=item.archive_path,
                timeout=settings.callback_timeout_seconds,
            )
            item.callback_sent()
            loguru.logger.info(f"Reported archive {item.id} to '{librarian_name}'.")
        except Exception as exc:
            error = str(exc)[:1024]
            if item.callback_attempts >= settings.callback_max_attempts:
                item.callback_failed(error)
                loguru.logger.warning(
                    f"Callback for {item.id} -> '{librarian_name}' failed "
                    f"after {item.callback_attempts} attempts: {exc}"
                )
            else:
                backoff = settings.callback_retry_base_seconds * 2 ** (item.callback_attempts - 1)
                item.callback_error(error, now + datetime.timedelta(seconds=backoff))
                loguru.logger.warning(
                    f"Callback for {item.id} -> '{librarian_name}' errored "
                    f"(attempt {item.callback_attempts}), retrying in {backoff:.0f}s: {exc}"
                )
        session.commit()
        return True
    finally:
        session.close()
