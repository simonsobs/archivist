import uuid

from fastapi import Depends, Response
from loguru import logger
from sqlalchemy.orm import Session

from archivist.api import router
from archivist.api.auth import SubmitterDependency
from archivist.core.models import ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.database import yield_session
from archivist.orm import Archive, Manifest, ManifestEntry
from archivist.settings import Settings, get_settings


@router.post("/archive", response_model=ManifestResponse | ManifestFailedResponse)
def archive(
    manifest_request: ManifestRequest,
    response: Response,
    submitter: SubmitterDependency,
    session: Session = Depends(yield_session),
    settings: Settings = Depends(get_settings),
):

    if submitter is not None and submitter != manifest_request.librarian_name:
        response.status_code = 403
        logger.error(f"Client '{submitter}' submitted a manifest claiming to be '{manifest_request.librarian_name}'.")
        return ManifestFailedResponse(error="Token does not match the submitting librarian.")

    # Here you would implement the logic to handle the archiving process
    # For now, we will just return a dummy response

    manifest_id = manifest_request.manifest_id
    total_size = sum(entry.size for entry in manifest_request.archive_files)
    if total_size > settings.maximal_size_bytes:  # Example size limit of 1GB
        response.status_code = 400
        logger.error(
            f"Archiving manifest from librarian '{manifest_request.librarian_name}' failed: total size {total_size} exceeds limit of {settings.maximal_size_bytes} bytes"
        )
        return ManifestFailedResponse(error="The total size of the files exceeds the allowed limit.")

    # Manifests are immutable and identified by the Librarian-minted
    # manifest_id, so that id doubles as an idempotency key. Archivist queues
    # asynchronously over HTTP and returns immediately, so a lost response
    # will make the Librarian retry; a resend must be safe. Fingerprint the
    # incoming payload as the sorted (name, checksum) of its files.
    incoming_files = sorted((entry.name, entry.checksum) for entry in manifest_request.archive_files)

    manifest = Manifest.get_or_create(
        session,
        manifest_id=manifest_id,
        librarian_name=manifest_request.librarian_name,
        archive_name=manifest_request.archive_name,
    )

    if manifest.entries:
        existing_files = sorted((entry.name, entry.checksum) for entry in manifest.entries)
        if existing_files == incoming_files:
            # Same id, same content: the retry case. Noop; report the id and
            # leave the already-queued archive untouched.
            logger.info(f"Manifest {manifest_id} already received; returning existing archive job.")
            return ManifestResponse(manifest_id=str(manifest_id), archive_id=str(manifest.archive.id))
        # Same id, different content: immutability violated. Reject loudly
        # rather than silently mutating the manifest or dropping the change.
        response.status_code = 409
        logger.error(
            f"Manifest {manifest_id} resubmitted with different content from librarian "
            f"'{manifest_request.librarian_name}'; manifests are immutable."
        )
        return ManifestFailedResponse(
            error="A manifest with this id already exists with different content; manifests are immutable."
        )

    # Attach entries and the archive job through relationships so the FKs
    # resolve and a single commit cascade-persists everything.
    manifest.entries = [
        ManifestEntry(
            name=entry.name,
            create_time=entry.create_time,
            size=entry.size,
            checksum=entry.checksum,
            uploader=entry.uploader,
            source=entry.source,
            instance_path=entry.instance_path,
            instance_create_time=entry.instance_create_time,
            instance_available=entry.instance_available,
            outgoing_transfer_id=entry.outgoing_transfer_id,
        )
        for entry in manifest_request.archive_files
    ]
    manifest.total_size_bytes = total_size
    manifest.file_count = len(manifest_request.archive_files)

    logger.info(
        f"Archiving manifest {manifest_id} from librarian '{manifest_request.librarian_name}': {len(manifest_request.archive_files)} file(s), {total_size} bytes total"
    )

    item = Archive.new_item(manifest=manifest, archive_root=settings.archive_root)
    session.add(item)
    session.commit()

    return ManifestResponse(manifest_id=str(manifest_id), archive_id=str(item.id))
