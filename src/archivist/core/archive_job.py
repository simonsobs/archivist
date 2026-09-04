# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with archives."""

from pathlib import Path

from loguru import logger

from .models import ManifestRequest


class ArchiveJob:
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

    def _expand_directory(self, src_path, entry):
        """Expand a directory manifest entry into one triple per contained file.

        The Librarian sends a directory's `size` as the sum of the files it
        holds, which says nothing about any individual file. Storage checks
        completeness per destination path, so a directory entry can never be
        verified as it stands. Walking it gives each file its own size, which
        makes verification meaningful and -- because already-correct files are
        skipped -- makes a partial copy resume rather than start over.

        The declared aggregate is logged as a cross-check rather than enforced.
        It is the only Librarian-supplied guarantee here -- the per-file sizes
        come from disk -- but how the Librarian computes a directory's size is
        not pinned down by the contract, and a hard gate on an off-by-a-little
        definition would fail every directory manifest. Warn, and let the
        per-file checks do the real work.
        """
        expanded = []
        total = 0

        for path in sorted(src_path.rglob("*")):
            # Follows symlinks, as `shutil.copy2` does when storing, so verify
            # and store agree on what a symlinked entry weighs. A broken
            # symlink is skipped here and shows up as an aggregate mismatch.
            if not path.is_file():
                continue
            size = path.stat().st_size
            total += size
            expanded.append((path, Path(self._archive_root) / path.relative_to(self._local_root), size))

        if total != entry["size"]:
            logger.warning(
                f"Directory {src_path} holds {total} bytes across {len(expanded)} files, but the "
                f"manifest declares {entry['size']} (difference {total - entry['size']}). Archiving "
                "what is on disk."
            )

        return expanded

    def create_archive(self):
        """Create the archive based on the manifest or paths."""
        # Placeholder for archive creation logic
        if self._type == "posix":
            src_dst_paths = []
            for entry in self._manifest["store_files"]:
                src_path = Path(entry["instance_path"])
                if src_path.is_dir():
                    src_dst_paths.extend(self._expand_directory(src_path, entry))
                    continue
                dst_path = Path(self._archive_root) / src_path.relative_to(self._local_root)
                src_dst_paths.append((src_path, dst_path, entry["size"]))
            return src_dst_paths

        elif self._type == "hpss":
            # Implement logic for creating an HPSS archive
            # Call subprocess to create the archive using HPSS commands
            pass
