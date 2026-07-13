from archivist.core.archive_job import ArchiveJob
from archivist.settings import Settings
from archivist.storage.base import Storage


class StorageHPSS(Storage):
    """Store archives to HPSS tapes."""

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
