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

    @staticmethod
    def _entry_satisfied(dst_path: Path, expected_size: int) -> bool:
        """True if dst_path exists as a regular file of the expected size."""
        return dst_path.is_file() and dst_path.stat().st_size == expected_size

    def _copy_files(self, file_list: list[tuple[Path, Path, int]]) -> None:
        """Copy every entry, then raise if any of them failed.

        One unreadable file does not abandon the rest of the manifest: a
        manifest can be a terabyte across hundreds of entries, and stopping at
        the first error throws away every copy that would have succeeded after
        it. Whatever did copy stays on disk and is skipped on the next run;
        the raise is what stops the archive being reported as complete.
        """
        errors: list[tuple[Path, Exception]] = []

        for src_path, dst_path, expected_size in file_list:
            if self._entry_satisfied(dst_path, expected_size):
                logger.debug(f"Skipping already-present {dst_path} (size {expected_size})")
                continue
            try:
                os.makedirs(dst_path.parent, exist_ok=True)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)
            except OSError as err:
                logger.exception(f"Failed to copy {src_path} -> {dst_path}")
                errors.append((src_path, err))

        if errors:
            first_path, first_error = errors[0]
            raise RuntimeError(
                f"{len(errors)} of {len(file_list)} entries failed to copy; first was {first_path}: {first_error!r}"
            )

    def _store(self, archive: ArchiveJob) -> "StorageDisk":
        """Copy the archive's files into a per-manifest subdirectory of archive_root."""
        self._archive = archive
        paths = self._archive.create_archive()

        self._future = StorageDisk._executor.submit(self._copy_files, paths)

        return self

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        """Extract files from tar archives."""

    def _verify(self, archive: ArchiveJob) -> bool:
        """Return True only if the destination already fully satisfies the manifest."""

        paths = archive.create_archive()
        for src_path, dst_path, expected_size in paths:
            if not self._entry_satisfied(dst_path, expected_size):
                logger.debug(f"Missing or incorrect {dst_path} (expected size {expected_size})")
                return False
        return True
