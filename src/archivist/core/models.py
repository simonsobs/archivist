"""
Pydantic modems for the admin endpoints
"""

from datetime import datetime

from pydantic import BaseModel


class ManifestEntry(BaseModel):
    name: str
    "The name of the file."
    create_time: datetime
    "The time the file was created."
    size: int
    "The size of the file in bytes."
    checksum: str
    "The checksum of the file."
    uploader: str
    "The uploader of the file."
    source: str
    "The source of the file."

    instance_path: str
    "The path to the instance on the store."
    instance_create_time: datetime
    "The time the instance was created."
    instance_available: bool
    "Whether the instance is available or not. If not, no outgoing transfer is created."

    outgoing_transfer_id: int
    "The ID of the outgoing transfer, if it exists."


class ManifestRequest(BaseModel):
    manifest_id: str
    "The ID of the manifest."

    librarian_name: str
    "The name of the librarian that generated this manifest."

    archive_files: list[ManifestEntry]
    "The files on the archive."


class ManifestResponse(BaseModel):
    archive_id: str
    "The ID of the archive."

    manifest_id: str
    "The ID of the manifest."


class ManifestFailedResponse(BaseModel):
    error: str
    "The error message indicating why the manifest request failed."
