# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.storage.storage_hpss.StorageHPSS (currently a stub backend)."""

import unittest

from archivist.storage.storage_hpss import StorageHPSS


class TestStorageHPSS(unittest.TestCase):
    def test_construction_takes_no_arguments(self):
        storage = StorageHPSS()
        self.assertIsInstance(storage, StorageHPSS)

    def test_store_is_a_noop_stub(self):
        storage = StorageHPSS()
        self.assertIsNone(storage.store(archive=None))

    def test_extract_is_a_noop_stub(self):
        storage = StorageHPSS()
        self.assertIsNone(storage.extract(archive_name="a", storage_info={}, outdir="/tmp/out"))


if __name__ == "__main__":
    unittest.main()
