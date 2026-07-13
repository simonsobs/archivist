import os
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from loguru import logger

from archivist.core.archive_job import ArchiveJob
from archivist.settings import Settings
from archivist.storage.base import Storage


class StorageDisk(Storage):
    """Simple filesystem storage.

    This class just keeps archives in subdirectories within a top-level location
    (``settings.archive_root``). Useful for testing and for archiving to "slow"
    storage that provides a POSIX API.

    Copies run in a shared background thread pool (sized by
    ``settings.storage_threads``) so that ``_store`` returns immediately; callers
    check ``future`` to see when the copy has finished.
    """

    _executor: ThreadPoolExecutor | None = None

    def __init__(self, settings: Settings | None = None):
        super().__init__(settings=settings)
        self._archive = None
        self._future: Future | None = None

        if StorageDisk._executor is None:
            max_workers = self._settings.storage_threads if self._settings else 4
            StorageDisk._executor = ThreadPoolExecutor(max_workers=max_workers)

    @property
    def future(self) -> Future | None:
        """The Future tracking the in-progress (or completed) copy, if any."""
        return self._future

    def _copy_files(self, file_list: list[tuple[Path, Path]]) -> None:
        """Copy each path in file_list into dest_dir."""
        for src_path, dst_path in file_list:
            os.makedirs(dst_path.parent, exist_ok=True)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dst_path)

    def _store(self, archive: ArchiveJob) -> "StorageDisk":
        """Copy the archive's files into a per-manifest subdirectory of archive_root."""
        self._archive = archive
        paths = self._archive.create_archive()

        self._future = StorageDisk._executor.submit(self._copy_files, paths)

        return self

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        """Extract files from tar archives."""
        pass
