from typing import Any

from fastapi import Depends

from archivist.api import health_router
from archivist.settings import Settings, get_settings


@health_router.get("/health")
def health(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Health check endpoint used by orchestrators/load balancers to confirm
    the server is up and responding.
    """

    return_dict = {"name": settings.displayed_site_name, "status": "ok"}

    return return_dict
