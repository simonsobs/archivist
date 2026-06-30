# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with archives."""

import subprocess


class Archive(object):
    """Class representing a single archive in a storage system.

    When listing objects in the manifest or paths list, directories can be specified
    instead of files.  This list of objects represents the most fine-grained set of
    things that can be extracted later, and the list of things which will be indexed
    by a registry.

    Args:
        manifest (str):  Path to a manifest file listing the files / directories
            contained in the archive.
        paths (list):  Alternatively list the full set of files / directories contained
            in the archive.
        root (str):  The common root filesystem location for building relative paths
            for all objects.

    """

    def __init__(self, manifest=None, paths=None, root=None, type=None):
        self._manifest = manifest
        self._paths = paths
        self._root = root
        self._type = type
        self._checksum = None  # Placeholder for checksum value

    @property
    def paths(self):
        return self._paths

    @property
    def root(self):
        return self._root

    @property
    def checksum(self):
        """Return the checksum of the archive."""

    def create_archive(self):
        """Create the archive based on the manifest or paths."""
        # Placeholder for archive creation logic
        if self._type == "posix":
            # Implement logic for creating a POSIX archive
            pass
        elif self._type == "hpss":
            # Implement logic for creating an HPSS archive
            # Call subprocess to create the archive using HPSS commands
            pass
