# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.storage.base.Storage."""

import unittest

from archivist.storage.base import Storage


class TestStorageBase(unittest.TestCase):
    def test_store_raises_not_implemented(self):
        storage = Storage()
        with self.assertRaises(NotImplementedError):
            storage.store(archive=None)

    def test_extract_raises_not_implemented(self):
        storage = Storage()
        with self.assertRaises(NotImplementedError):
            storage.extract(archive_name="a", storage_info={}, outdir="/tmp/out")

    def test_settings_defaults_to_none(self):
        storage = Storage()
        self.assertIsNone(storage._settings)

    def test_settings_stored_when_provided(self):
        sentinel = object()
        storage = Storage(settings=sentinel)
        self.assertIs(storage._settings, sentinel)


class _RecordingStorage(Storage):
    """Subclass that records the arguments _extract/_store receive."""

    def __init__(self, settings=None):
        super().__init__(settings=settings)
        self.store_calls = []
        self.extract_calls = []

    def _store(self, archive):
        self.store_calls.append(archive)
        return {"stored": True}

    def _extract(self, archive_name, storage_info, outdir, paths=None):
        self.extract_calls.append((archive_name, storage_info, outdir, paths))


class TestStorageDelegation(unittest.TestCase):
    def test_store_delegates_to_store_impl_and_returns_its_value(self):
        storage = _RecordingStorage()
        result = storage.store(archive="my-archive")

        self.assertEqual(storage.store_calls, ["my-archive"])
        self.assertEqual(result, {"stored": True})

    def test_extract_ignores_caller_supplied_paths(self):
        """
        `Storage.extract()` currently hardcodes `paths=None` in its call to
        `_extract()` regardless of what the caller passes in -- this test
        documents that existing (surprising) behavior.
        """
        storage = _RecordingStorage()
        storage.extract(archive_name="a", storage_info={"k": "v"}, outdir="/tmp/out", paths=["only", "these"])

        self.assertEqual(storage.extract_calls, [("a", {"k": "v"}, "/tmp/out", None)])


if __name__ == "__main__":
    unittest.main()
