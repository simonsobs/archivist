from archivist.core.archive_job import ArchiveJob
from archivist.settings import Settings


class Storage(object):
    """Base class representing an archive storage system."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings

    def _store(self, archive: ArchiveJob) -> "Storage":
        raise NotImplementedError("Fell through to base class")

    def store(self, archive: ArchiveJob) -> "Storage":
        """Store an archive.

        Args:
            archive (ArchiveJob):  The archive to store.

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

    def _verify(self, archive: ArchiveJob) -> bool:
        raise NotImplementedError("Fell through to base class")

    def verify(self, archive: ArchiveJob) -> bool:
        """Return True only if the destination already fully satisfies the manifest."""
        return self._verify(archive)
