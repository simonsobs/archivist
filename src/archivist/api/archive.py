import json
import uuid

from fastapi import Depends, Response

from archivist.api import router
from archivist.core.models import Archive, ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.queue import ArchiveQueue, get_queue
from archivist.settings import Settings, get_settings


@router.post("/archive", response_model=ManifestResponse | ManifestFailedResponse)
def archive(
    manifest_request: ManifestRequest,
    response: Response,
    queue: ArchiveQueue = Depends(get_queue),
    settings: Settings = Depends(get_settings),
):
    """
    Endpoint to archive a file.
    """
    # Here you would implement the logic to handle the archiving process
    # For now, we will just return a dummy response

    total_size = sum(entry.size for entry in manifest_request.store_files)
    if total_size > settings.maximal_size_bytes:  # Example size limit of 1GB
        response.status_code = 400
        return ManifestFailedResponse(error="The total size of the files exceeds the allowed limit.")

    manifest_id = uuid.uuid4()

    archive = Archive(
        manifest_id=str(manifest_id),
        manifest=json.dumps(manifest_request),
        paths=[entry.instance_path for entry in manifest_request.store_files],
        root=settings.storage_root,  # Example root path
    )

    # TODO: Add the archive to a queue for processing
    queue.enqueue_archive(archive)

    return ManifestResponse(
        manifest_id=str(manifest_id),
    )
