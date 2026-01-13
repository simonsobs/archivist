# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with storage systems."""


class Storage(object):
    """Base class representing an archive storage system.
    """
    def __init__(self):
        pass

    def _store(self, archive):
        raise NotImplementedError("Fell through to base class")

    def store(self, archive):
        """Store an archive.

        Args:
            archive (Archive):  The archive to store.

        Returns:
            (dict):  Metadata specific to the storage system.  Used when registering
                the archive.

        """
        return self._store(archive)

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        raise NotImplementedError("Fell through to base class")

    def extract(self, archive_name, storage_info, outdir, paths=None):
        """Extract objects from an archive.

        The archive name and additional storage metadata is used to locate and extract
        one or more paths from the archive.  `storage_info` should be the same
        metadata returned by the call to `store()` and kept in the registry.

        Args:
            archive_name (str):  The name of the archive to remove.
            storage_info (dict):  Additional storage-system specific metadata.
            outdir (str):  The top-level output directory where extracted files
                should be placed.
            paths (list):  Optional list of objects to extract.  If None, the
                entire archive is extracted.

        Returns:
            (None)

        """
        self._extract(archive_name, storage_info, outdir, paths=None)


class StorageDisk(Storage):
    """Simple filesystem storage.

    This class just keeps archives in subdirectories within a top-level location.
    Useful for testing and for archiving to "slow" storage that provides a POSIX
    API.

    Args:
        directory (str):  The top-level location for storing archives.

    """
    def __init__(self, directory):
        self._directory = directory
        super().__init__()

    def _store(self, archive):
        """Tar the archive files into the storage directory."""
        pass

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        """Extract files from tar archives."""
        pass


class StorageHPSS(Storage):
    """Store archives to HPSS tapes.
    """
    def __init__(self):
        super().__init__()

    def _store(self, archive):
        """Use HTAR to archive files.
        The tape list is returned for including in the registry entry.
        """
        pass

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        """Extract files from HTAR archives."""
        pass
