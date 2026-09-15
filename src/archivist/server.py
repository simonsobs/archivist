"""
The Archivist v2.0 server.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from archivist.tasks.archive import find_orphaned_archives, reconcile_orphaned_archives

from .settings import server_settings

_archive_stop_event = threading.Event()


def _archive_worker_loop():
    from loguru import logger

    from .settings import get_settings
    from .tasks.archive import start_archive

    poll_interval = get_settings().worker_poll_interval_seconds
    while not _archive_stop_event.is_set():
        try:
            did_work = start_archive(librarian_name=server_settings.name)
        except Exception:  # noqa: BLE001
            logger.exception("Archive worker iteration failed")
            did_work = False
        # Only pause when the queue was empty, so a backlog still drains at
        # full speed.
        if not did_work:
            _archive_stop_event.wait(poll_interval)


def _status_worker_loop():
    from loguru import logger

    from .settings import get_settings
    from .tasks.archive import process_status_queue

    poll_interval = get_settings().worker_poll_interval_seconds
    while not _archive_stop_event.is_set():
        try:
            process_status_queue()
        except Exception:  # noqa: BLE001
            logger.exception("Archive worker iteration failed")
        # Always pause: this loop polls futures that take minutes to hours, and
        # it reports "handled" even when it merely re-queued an unfinished one,
        # so there is no busy case worth spinning for.
        _archive_stop_event.wait(poll_interval)


def _callback_worker_loop():
    from loguru import logger

    from .settings import get_settings
    from .tasks.callback import process_callbacks

    poll_interval = get_settings().callback_poll_interval_seconds
    while not _archive_stop_event.is_set():
        try:
            did_work = process_callbacks()
        except Exception:  # noqa: BLE001
            logger.exception("Callback worker iteration failed")
            did_work = False
        # The callback queue is backoff-driven, so idle between polls instead
        # of spinning when there is nothing due.
        if not did_work:
            _archive_stop_event.wait(poll_interval)


@asynccontextmanager
async def startup_shutdown_server(app: FastAPI):
    """
    Lifespan event that posts to the slack hook once
    the FastAPI server starts up and shuts down.
    """
    from loguru import logger

    logger.info("Archivist server starting up")

    # Only the snapshot happens here -- one indexed query. Verification stats
    # every file of every unfinished archive, which is minutes over network
    # storage, and uvicorn does not bind its socket until this handler returns.
    # Doing it inline would mean the port stays closed, and the Librarian's
    # POSTs are refused rather than queued, for the whole of that window.
    orphan_ids = find_orphaned_archives()
    if orphan_ids:
        logger.info(f"Found {len(orphan_ids)} archive(s) to reconcile; verifying in the background.")

    thread_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="worker")
    # Safe to run alongside the workers because the orphan set was captured
    # before any of them started: a manifest arriving from here on becomes
    # `consumed` under a worker and can never be mistaken for an orphan.
    thread_pool.submit(reconcile_orphaned_archives, orphan_ids)
    thread_pool.submit(_archive_worker_loop)
    thread_pool.submit(_status_worker_loop)
    thread_pool.submit(_callback_worker_loop)
    yield

    logger.info("Archivist server shutting down")
    _archive_stop_event.set()
    thread_pool.shutdown(wait=True)


def main() -> FastAPI:
    from loguru import logger

    logger.info("Starting Archivist server.")
    logger.debug("Creating FastAPI app instance.")

    app = FastAPI(
        title=server_settings.displayed_site_name,
        description=server_settings.displayed_site_description,
        openapi_url="/api/v2/openapi.json" if server_settings.debug else None,
        lifespan=startup_shutdown_server,
    )

    logger.debug("Adding API router.")

    from .api import health_router
    from .api import router as api_router

    app.include_router(api_router)
    app.include_router(health_router)

    return app
