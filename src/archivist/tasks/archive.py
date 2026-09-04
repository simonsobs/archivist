import queue
from collections.abc import Callable
from time import sleep

import loguru
from sqlalchemy.orm import Session

from archivist.core import storage_factory
from archivist.core.archive_job import ArchiveJob
from archivist.core.models import ManifestEntry
from archivist.database import get_session
from archivist.orm.archive import Archive
from archivist.queue import get_status_queue
from archivist.settings import get_settings


def start_archive(
    librarian_name: str,
    store_files: bool = True,
    session_maker: Callable[[], Session] = get_session,
) -> bool:
    """
    Dequeue the next archive job and hand it to a storage backend.

    Called directly from the background worker thread loop (not a FastAPI
    route), so dependencies are resolved here rather than via `Depends`.
    Takes ``session_maker`` (rather than calling ``get_session`` inline) so a
    future task-based runner can inject it; returns ``True`` when a job was
    picked up and ``False`` when the queue was empty.
    """
    status_queue = get_status_queue()
    settings = get_settings()
    session = session_maker()
    try:
        archive_item = Archive.dequeue(session)
        if archive_item is None:
            return False

        manifest = {
            "store_files": [
                ManifestEntry.model_validate(entry, from_attributes=True).model_dump()
                for entry in archive_item.manifest.entries
            ]
        }
        loguru.logger.info(f"Archive Item: {manifest}, {type(archive_item)}")
        archive = ArchiveJob(
            manifest=manifest,
            manifest_id=archive_item.manifest_id,
            local_root=settings.local_root,
            archive_root=archive_item.archive_root,
            type=settings.archive_type,
        )
        storage = storage_factory[settings.archive_type](settings=settings)
        storage_task = storage.store(archive)
        status_queue.enqueue(storage_task)
        return True
    finally:
        session.close()


def process_status_queue(session_maker: Callable[[], Session] = get_session) -> bool:
    """
    Process the status queue to check for completed or failed archive tasks.

    Called directly from the background worker thread loop (not a FastAPI
    route), so dependencies are resolved here rather than via `Depends`.
    Returns ``True`` when a task was handled and ``False`` when the queue was
    empty, mirroring librarian's ``check_on_consumed``.
    """
    status_queue = get_status_queue()
    try:
        storage_task = status_queue.dequeue(block=False)
    except queue.Empty:
        return False

    try:
        # Not an f-string: this runs on every iteration of a hot loop, and an
        # f-string is built whether or not DEBUG is enabled. loguru defers the
        # formatting until it knows the record will be emitted.
        loguru.logger.debug("Processing status queue for storage task: {}", storage_task._archive.manifest_id)
        if storage_task.future.done():
            loguru.logger.debug(f"Storage task for archive {storage_task._archive.manifest_id} future completed.")
            session = session_maker()
            try:
                item = session.query(Archive).filter_by(manifest_id=storage_task._archive.manifest_id).first()
                loguru.logger.debug(
                    f"Retrieved Archive item for manifest_id {storage_task._archive.manifest_id}: {item}"
                )
                if item is None:
                    return True

                # `done()` is True for a future that raised, so the exception
                # has to be read explicitly. Without this a failed or partial
                # copy is reported to the Librarian as a success, and the
                # error is discarded rather than logged.
                store_error = storage_task.future.exception()
                if store_error is not None:
                    loguru.logger.error(f"Archive {storage_task._archive.manifest_id} failed to store: {store_error!r}")
                    item.fail(session)
                    return True

                try:
                    item.archive_path = storage_task._archive.archive_root
                    if item.manifest.librarian_name == get_settings().cli_librarian_name:
                        item.skip_callback()
                    else:
                        item.callback_pending()
                    item.complete(session)
                    loguru.logger.info(f"Archive {storage_task._archive.manifest_id} completed successfully.")
                except Exception:  # noqa: BLE001
                    loguru.logger.exception(f"Archive {storage_task._archive.manifest_id} failed to store.")
                    item.fail(session)
            finally:
                session.close()
        else:
            loguru.logger.debug(
                f"Storage task for archive {storage_task._archive.manifest_id} future not completed yet."
            )
            status_queue.enqueue(storage_task)

        status_queue.task_done()
        return True
    except Exception as e:  # noqa: BLE001
        loguru.logger.error(f"Error processing status queue: {e}")
        sleep(1)  # Sleep for a short duration to avoid busy waiting
        return True


def reconcile_orphaned_archives(
    session_maker: Callable[[], Session] = get_session,
) -> None:
    """
    On startup, re-drive archive jobs orphaned by a crash.

    A row that was consumed but never completed lost its in-memory Future when
    the process died. For each such row: verify the destination against the
    manifest; if already satisfied, complete it; otherwise requeue it (up to
    settings.max_archive_retries) so the normal worker loop re-runs the now
    idempotent store(), or fail it once the retry cap is hit.
    """
    settings = get_settings()
    session = session_maker()
    try:
        orphans = session.query(Archive).filter_by(consumed=True, completed=False).all()
        for item in orphans:
            try:
                manifest = {
                    "store_files": [
                        ManifestEntry.model_validate(entry, from_attributes=True).model_dump()
                        for entry in item.manifest.entries
                    ]
                }
                archive = ArchiveJob(
                    manifest=manifest,
                    manifest_id=item.manifest_id,
                    local_root=settings.local_root,
                    archive_root=item.archive_root,
                    type=settings.archive_type,
                )
                storage = storage_factory[settings.archive_type](settings=settings)
                if storage.verify(archive):
                    item.archive_path = archive.archive_root
                    item.complete(session)
                    loguru.logger.info(f"Reconciled orphan {item.id}: already complete.")
                elif item.retries >= settings.max_archive_retries:
                    loguru.logger.error(f"Orphan {item.id} exceeded max_archive_retries; failing.")
                    item.fail(session)
                else:
                    item.requeue(session)
                    loguru.logger.info(f"Requeued orphan {item.id} (retry {item.retries}).")
            except Exception:  # noqa: BLE001
                loguru.logger.exception(f"Failed to reconcile orphan {getattr(item, 'manifest_id', '?')}; skipping.")
    finally:
        session.close()
