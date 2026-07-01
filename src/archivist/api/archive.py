import uuid

from fastapi import Depends, Response
from loguru import logger

from archivist.api import router
from archivist.core.models import Archive, ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.queue import ArchiveQueue, get_archive_queue
from archivist.settings import Settings, get_settings


@router.post("/archive", response_model=ManifestResponse | ManifestFailedResponse)
def archive(
    manifest_request: ManifestRequest,
    response: Response,
    queue: ArchiveQueue = Depends(get_archive_queue),
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
        logger.error(
            f"Archiving manifest from librarian '{manifest_request.librarian_name}' failed: total size {total_size} exceeds limit of {settings.maximal_size_bytes} bytes"
        )
        return ManifestFailedResponse(error="The total size of the files exceeds the allowed limit.")

    manifest_id = uuid.uuid4()

    logger.info(
        f"Archiving manifest {manifest_id} from librarian '{manifest_request.librarian_name}': {len(manifest_request.store_files)} file(s), {total_size} bytes total"
    )

    archive = Archive(
        manifest_id=str(manifest_id),
        manifest=manifest_request.model_dump_json(),
        paths=[entry.instance_path for entry in manifest_request.store_files],
        root=settings.storage_root,  # Example root path
    )

    # TODO: Add the archive to a queue for processing
    # queue.enqueue_archive(archive)

    return ManifestResponse(
        manifest_id=str(manifest_id),
    )
