# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.storage.storage_disk.StorageDisk."""

import unittest

import pytest
from conftest import make_manifest_entry

from archivist.core.archive import Archive
from archivist.storage.storage_disk import StorageDisk


@pytest.mark.usefixtures("use_settings")
class TestStorageDiskBase(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _inject(self, use_settings, local_root, archive_root):
        self.settings = use_settings
        self.local_root = local_root
        self.archive_root = archive_root


class TestStoreSingleFile(TestStorageDiskBase):
    def test_store_copies_file_to_archive_root(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")

        manifest = {"store_files": [make_manifest_entry(instance_path=str(source))]}
        archive = Archive(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

        storage = StorageDisk(settings=self.settings)
        task = storage.store(archive)
        task.future.result(timeout=5)

        dest = self.archive_root / "file.txt"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "hello")

    def test_store_copies_nested_file_preserving_relative_path(self):
        nested_dir = self.local_root / "sub" / "dir"
        nested_dir.mkdir(parents=True)
        source = nested_dir / "nested.txt"
        source.write_text("nested-content")

        manifest = {"store_files": [make_manifest_entry(instance_path=str(source))]}
        archive = Archive(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

        storage = StorageDisk(settings=self.settings)
        task = storage.store(archive)
        task.future.result(timeout=5)

        dest = self.archive_root / "sub" / "dir" / "nested.txt"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "nested-content")

    def test_store_returns_self_with_archive_and_future(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")

        manifest = {"store_files": [make_manifest_entry(instance_path=str(source))]}
        archive = Archive(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

        storage = StorageDisk(settings=self.settings)
        result = storage.store(archive)
        result.future.result(timeout=5)

        self.assertIs(result, storage)
        self.assertIs(result._archive, archive)
        self.assertIsNotNone(result.future)


class TestStoreDirectory(TestStorageDiskBase):
    def test_store_copies_directory_tree(self):
        src_dir = self.local_root / "adir"
        src_dir.mkdir()
        (src_dir / "inner.txt").write_text("inner-content")

        manifest = {"store_files": [make_manifest_entry(instance_path=str(src_dir))]}
        archive = Archive(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

        storage = StorageDisk(settings=self.settings)
        task = storage.store(archive)
        task.future.result(timeout=5)

        dest_file = self.archive_root / "adir" / "inner.txt"
        self.assertTrue(dest_file.exists())
        self.assertEqual(dest_file.read_text(), "inner-content")


class TestSharedExecutor(TestStorageDiskBase):
    def test_executor_is_shared_across_instances(self):
        first = StorageDisk(settings=self.settings)
        second = StorageDisk(settings=self.settings)
        self.assertIs(first._executor, second._executor)
        self.assertIs(StorageDisk._executor, first._executor)


class TestExtractStub(TestStorageDiskBase):
    def test_extract_is_currently_a_noop_stub(self):
        storage = StorageDisk(settings=self.settings)
        self.assertIsNone(storage.extract(archive_name="a", storage_info={}, outdir=str(self.archive_root)))


if __name__ == "__main__":
    unittest.main()
