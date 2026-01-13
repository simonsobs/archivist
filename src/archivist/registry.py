# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Classes for working with archive registries."""


class Registry(object):
    """Base class representing a registry of archives.

    """
    def __init__(self):
        pass

    def _register(self, archive, storage_info):
        raise NotImplementedError("Fell through to base class")

    def register(self, archive, storage_info):
        """Store an archive in the registry.

        Args:
            archive (Archive):  The archive to register.
            storage_info (dict):  Storage-system specific metadata.

        Returns:
            (None)

        """
        self._register(archive, storage_info)

    def _remove(self, archive_name):
        raise NotImplementedError("Fell through to base class")

    def remove(self, archive_name):
        """Remove an archive from the registry.

        Args:
            archive_name (str):  The name of the archive to remove.

        Returns:
            (None)

        """
        self._remove(archive_name)


class RegistrySqlite(Registry):
    """Simple class which registers archives in an SQLite DB."""
    def __init__(self):
        super().__init__()

    def _register(self, archive, storage_info):
        pass

    def _remove(self, archive_name):
        pass


class RegistryLibrarian(Registry):
    """Store archive metadata with with the librarian."""
    def __init__(self):
        super().__init__()

    def _register(self, archive, storage_info):
        pass

    def _remove(self, archive_name):
        pass
