# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with archives."""


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
    def __init__(self, manifest=None, paths=None, root=None):
        pass

    @property
    def paths(self):
        pass

    @property
    def root(self):
        pass

    @property
    def checksum(self):
        pass

