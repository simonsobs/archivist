# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with archives."""

from pathlib import Path

from .models import ManifestRequest


class ArchiveJob(object):
    """Class representing a single archive in a storage system.

    When listing objects in the manifest or paths list, directories can be specified
    instead of files.  This list of objects represents the most fine-grained set of
    things that can be extracted later, and the list of things which will be indexed
    by a registry.

    Args:
        manifest (str):  Path to a manifest file listing the files / directories
            contained in the archive.
        root (str):  The common root filesystem location for building relative paths
            for all objects.

    """

    def __init__(
        self,
        manifest: dict | None = None,
        manifest_id: str | None = None,
        local_root: str | None = None,
        archive_root: str | None = None,
        type: str | None = None,
    ):
        self._manifest = manifest
        self._manifest_id = manifest_id
        self._local_root = local_root
        self._archive_root = archive_root
        self._type = type
        self._checksum = None  # Placeholder for checksum value

    @property
    def local_root(self):
        return self._local_root

    @property
    def archive_root(self):
        return self._archive_root

    @property
    def checksum(self):
        return self._checksum

    @property
    def manifest(self):
        return self._manifest

    @property
    def manifest_id(self):
        return self._manifest_id

    def __repr__(self):
        return f"<Archive manifest_id={self._manifest_id} type={self._type}>, <manifest={self._manifest}>, <local_root={self._local_root}>, <archive_root={self._archive_root}>"

    def create_archive(self):
        """Create the archive based on the manifest or paths."""
        # Placeholder for archive creation logic
        if self._type == "posix":
            src_dst_paths = []
            for entry in self._manifest["store_files"]:
                src_path = Path(entry["instance_path"])
                dst_path = Path(self._archive_root) / src_path.relative_to(self._local_root)
                src_dst_paths.append((src_path, dst_path, entry["size"]))
            return src_dst_paths

        elif self._type == "hpss":
            # Implement logic for creating an HPSS archive
            # Call subprocess to create the archive using HPSS commands
            pass
