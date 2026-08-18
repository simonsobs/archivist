import json
import uuid

from fastapi import Depends, Response

from archivist.api import router
from archivist.core.archive_job import ArchiveJob
from archivist.core.models import ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.settings import Settings, get_settings


@router.post("/extract", response_model=ManifestResponse | ManifestFailedResponse)
def extract(
    manifest_request: ManifestRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
):
    """
    Endpoint to extract a file.
    """
    # Here you would implement the logic to handle the extraction process
    # For now, we will just return a dummy response
