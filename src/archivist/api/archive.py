import uuid

from fastapi import Depends, Response
from loguru import logger
from sqlalchemy.orm import Session

from archivist.api import router
from archivist.core.models import ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.database import yield_session
from archivist.orm.archivequeue import ArchiveQueue
from archivist.settings import Settings, get_settings


@router.post("/archive", response_model=ManifestResponse | ManifestFailedResponse)
def archive(
    manifest_request: ManifestRequest,
    response: Response,
    session: Session = Depends(yield_session),
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

    item = ArchiveQueue.new_item(
        manifest_id=str(manifest_id),
        manifest=manifest_request.model_dump_json(),
        paths=[entry.instance_path for entry in manifest_request.store_files],
        root=settings.archive_root,
    )
    session.add(item)
    session.commit()

    return ManifestResponse(
        manifest_id=str(manifest_id),
    )
