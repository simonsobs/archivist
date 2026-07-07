import json
import queue
from time import sleep

import loguru
from sqlalchemy import inspect

from archivist.core import storage_factory
from archivist.core.archive import Archive
from archivist.database import get_session
from archivist.orm.archivequeue import ArchiveQueue
from archivist.queue import get_status_queue
from archivist.settings import get_settings


def start_archive(librarian_name: str, store_files: bool = True) -> None:
    """
    Start an archive process by sending a request to the archivist server.

    Called directly from the background worker thread loop (not a FastAPI
    route), so dependencies are resolved here rather than via `Depends`.
    """
    status_queue = get_status_queue()
    settings = get_settings()
    session = get_session()
    try:
        archive_item = ArchiveQueue.dequeue(session)
        if archive_item is not None:
            archive_dict = {c.key: getattr(archive_item, c.key) for c in inspect(archive_item).mapper.column_attrs}
            loguru.logger.info(f"Archive Item: {archive_dict}, {type(archive_item)}")
            archive = Archive(
                manifest=json.loads(archive_dict["manifest"]),
                manifest_id=archive_dict["manifest_id"],
                local_root=settings.local_root,
                archive_root=settings.archive_root,
                type=settings.archive_type,
            )
            storage = storage_factory[settings.archive_type](settings=settings)
            storage_task = storage.store(archive)
            status_queue.enqueue(storage_task)
    finally:
        session.close()


def process_status_queue() -> None:
    """
    Process the status queue to check for completed or failed archive tasks.

    Called directly from the background worker thread loop (not a FastAPI
    route), so dependencies are resolved here rather than via `Depends`.
    """
    status_queue = get_status_queue()
    try:
        storage_task = status_queue.dequeue(block=False)
        loguru.logger.debug(f"Processing status queue for storage task: {storage_task._archive}")
        if storage_task.future.done():
            loguru.logger.debug(f"Storage task for archive {storage_task._archive.manifest_id} future completed.")
            session = get_session()
            try:
                item = session.query(ArchiveQueue).filter_by(manifest_id=storage_task._archive.manifest_id).first()
                loguru.logger.debug(
                    f"Retrieved ArchiveQueue item for manifest_id {storage_task._archive.manifest_id}: {item}"
                )
                if item is None:
                    return
                try:
                    item.complete(session)
                    loguru.logger.info(f"Archive {storage_task._archive.manifest_id} completed successfully.")
                except Exception:
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
    except queue.Empty:
        pass
    except Exception as e:
        loguru.logger.error(f"Error processing status queue: {e}")
        sleep(1)  # Sleep for a short duration to avoid busy waiting
