# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Test top-level package imports and construction of the public classes."""

import unittest

import archivist
from archivist import ArchiveJob, RegistryLibrarian, RegistrySqlite, StorageDisk, StorageHPSS


class TestPackageImports(unittest.TestCase):
    def test_version_is_exposed(self):
        self.assertIsInstance(archivist.__version__, str)

    def test_construction(self):
        archive_job = ArchiveJob()
        reg_lib = RegistryLibrarian()
        reg_sql = RegistrySqlite()
        store_disk = StorageDisk()
        store_hpss = StorageHPSS()

        self.assertIsInstance(archive_job, ArchiveJob)
        self.assertIsInstance(reg_lib, RegistryLibrarian)
        self.assertIsInstance(reg_sql, RegistrySqlite)
        self.assertIsInstance(store_disk, StorageDisk)
        self.assertIsInstance(store_hpss, StorageHPSS)


if __name__ == "__main__":
    unittest.main()
