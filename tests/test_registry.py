# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.core.registry classes."""

import unittest

from archivist.core.registry import Registry, RegistryLibrarian, RegistrySqlite


class TestRegistryBase(unittest.TestCase):
    def test_register_raises_not_implemented(self):
        registry = Registry()
        with self.assertRaises(NotImplementedError):
            registry.register(archive=None, storage_info=None)

    def test_remove_raises_not_implemented(self):
        registry = Registry()
        with self.assertRaises(NotImplementedError):
            registry.remove(archive_name="foo")


class TestRegistrySubclasses(unittest.TestCase):
    def test_registry_sqlite_register_and_remove_are_noops(self):
        registry = RegistrySqlite()
        self.assertIsNone(registry.register(archive=None, storage_info=None))
        self.assertIsNone(registry.remove(archive_name="foo"))

    def test_registry_librarian_register_and_remove_are_noops(self):
        registry = RegistryLibrarian()
        self.assertIsNone(registry.register(archive=None, storage_info=None))
        self.assertIsNone(registry.remove(archive_name="foo"))


if __name__ == "__main__":
    unittest.main()
