import json
import uuid

from fastapi import Depends, Response

from archivist.api import router
from archivist.core.models import Archive, ManifestFailedResponse, ManifestRequest, ManifestResponse


@router.post("/archive", response_model=ManifestResponse | ManifestFailedResponse)
def archive(
    manifest_request: ManifestRequest,
    response: Response,
    queue: "Queue" = Depends(get_queue),  # noqa: F821
    settings: "Settings" = Depends(get_settings),  # noqa: F821
):
    """
    Endpoint to archive a file.
    """
    # Here you would implement the logic to handle the archiving process
    # For now, we will just return a dummy response

    # TODO: Implement the actual archiving logic here.

    # TODO: get the basic settings to know the type of archival store and the size of the
    #      archive manifest

    total_size = sum(entry.size for entry in manifest_request.store_files)
    if total_size > 1000000000:  # Example size limit of 1GB
        response.status_code = 400
        return ManifestFailedResponse(error="The total size of the files exceeds the allowed limit.")

    manifest_id = uuid.uuid4()

    archive = Archive(
        manifest_id=str(manifest_id),
        manifest=json.dumps(manifest_request),
        paths=[entry.instance_path for entry in manifest_request.store_files],
        root=settings.archive_root,  # Example root path
    )

    # TODO: Add the archive to a queue for processing
    queue.enqueue_archive(archive)

    return ManifestResponse(
        manifest_id=str(manifest_id),
    )
