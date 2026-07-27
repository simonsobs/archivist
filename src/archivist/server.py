"""
The Archivist v2.0 server.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .settings import server_settings

_archive_stop_event = threading.Event()


def _archive_worker_loop():
    from loguru import logger

    from .tasks.archive import start_archive

    while not _archive_stop_event.is_set():
        try:
            start_archive(librarian_name=server_settings.name)
        except Exception:
            logger.exception("Archive worker iteration failed")


def _status_worker_loop():
    from loguru import logger

    from .tasks.archive import process_status_queue

    while not _archive_stop_event.is_set():
        try:
            process_status_queue()
        except Exception:
            logger.exception("Archive worker iteration failed")


@asynccontextmanager
async def startup_shutdown_server(app: FastAPI):
    """
    Lifespan event that posts to the slack hook once
    the FastAPI server starts up and shuts down.
    """
    from loguru import logger

    from .database import create_all

    logger.info("Archivist server starting up")

    create_all()

    thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="worker")
    thread_pool.submit(_archive_worker_loop)
    thread_pool.submit(_status_worker_loop)
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
