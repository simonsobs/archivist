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
    store_name: str
    "The name of the store to get the manifest for."

    create_outgoing_transfers: bool = False
    "Whether to create outgoing transfers for the files in the manifest."

    destination_librarian: str = ""
    "The name of the librarian to send the files to, if create_outgoing_transfers is true."

    disable_store: bool = False
    "Whether to disable the store after creating the outgoing transfers."

    mark_local_instances_as_unavailable: bool = False
    "Mark the local instances as unavailable after creating the outgoing transfers."


class ManifestResponse(BaseModel):
    librarian_name: str
    "The name of the librarian that generated this manifest."

    store_name: str
    "The name of the store."

    store_files: list[ManifestEntry]
    "The files on the store."


class Archive(BaseModel):
    manifest: str
    "Path to a manifest file listing the files / directories contained in the archive."

    paths: list[str]
    "Alternatively list the full set of files / directories contained in the archive."

    root: str
    "The common root filesystem location for building relative paths for all objects."
