"""
The Archivist v2.0 server.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .settings import server_settings


@asynccontextmanager
async def slack_post_at_startup_shutdown(app: FastAPI):
    """
    Lifespan event that posts to the slack hook once
    the FastAPI server starts up and shuts down.
    """
    from loguru import logger

    logger.info("Archivist server starting up")
    yield
    logger.info("Archivist server shutting down")


def main() -> FastAPI:
    from loguru import logger

    logger.info("Starting Archivist server.")
    logger.debug("Creating FastAPI app instance.")

    app = FastAPI(
        title=server_settings.displayed_site_name,
        description=server_settings.displayed_site_description,
        openapi_url="/api/v2/openapi.json" if server_settings.debug else None,
        lifespan=slack_post_at_startup_shutdown,
    )

    logger.debug("Adding API router.")

    from .api import health_router
    from .api import router as api_router

    app.include_router(api_router)
    app.include_router(health_router)

    return app
