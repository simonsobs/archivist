# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Test package imports."""

import archivist
from archivist import Archive, RegistryLibrarian, RegistrySqlite, StorageDisk, StorageHPSS
from archivist import _version as pkg_version


def test_construction():
    archive = Archive(paths=[])
    reg_lib = RegistryLibrarian()
    reg_sql = RegistrySqlite()
    store_disk = StorageDisk(".")
    store_hpss = StorageHPSS()
