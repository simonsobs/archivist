# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.storage.storage_disk.StorageDisk."""

import unittest

import pytest
from conftest import make_manifest_entry

from archivist.core.archive_job import ArchiveJob
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
        archive = ArchiveJob(
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
        archive = ArchiveJob(
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
        archive = ArchiveJob(
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
        archive = ArchiveJob(
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


class TestEntrySatisfied(TestStorageDiskBase):
    def test_true_when_file_present_with_matching_size(self):
        dst = self.archive_root / "f.txt"
        dst.write_text("hello")  # 5 bytes
        self.assertTrue(StorageDisk._entry_satisfied(dst, 5))

    def test_false_when_missing(self):
        self.assertFalse(StorageDisk._entry_satisfied(self.archive_root / "nope.txt", 5))

    def test_false_when_size_mismatch(self):
        dst = self.archive_root / "f.txt"
        dst.write_text("hello")  # 5 bytes
        self.assertFalse(StorageDisk._entry_satisfied(dst, 99))

    def test_false_for_directory(self):
        d = self.archive_root / "adir"
        d.mkdir()
        self.assertFalse(StorageDisk._entry_satisfied(d, 0))


class TestIdempotentCopy(TestStorageDiskBase):
    def test_copy_files_skips_already_present_matching_file(self):
        src = self.local_root / "file.txt"
        src.write_text("original")
        dst = self.archive_root / "file.txt"
        dst.write_text("original")  # already there, same 8-byte size
        dst_mtime = dst.stat().st_mtime_ns

        storage = StorageDisk(settings=self.settings)
        storage._copy_files([(src, dst, 8)])

        # Untouched: the copy was skipped, so mtime is unchanged.
        self.assertEqual(dst.stat().st_mtime_ns, dst_mtime)

    def test_copy_files_recopies_when_size_differs(self):
        src = self.local_root / "file.txt"
        src.write_text("new-content")  # 11 bytes
        dst = self.archive_root / "file.txt"
        dst.write_text("stale")  # 5 bytes -> mismatch, must be recopied

        storage = StorageDisk(settings=self.settings)
        storage._copy_files([(src, dst, 11)])

        self.assertEqual(dst.read_text(), "new-content")

    def test_copy_files_copies_when_destination_missing(self):
        src = self.local_root / "file.txt"
        src.write_text("hello")
        dst = self.archive_root / "sub" / "file.txt"

        storage = StorageDisk(settings=self.settings)
        storage._copy_files([(src, dst, 5)])

        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(), "hello")


class TestVerify(TestStorageDiskBase):
    def _archive_for(self, source, size):
        manifest = {"store_files": [make_manifest_entry(instance_path=str(source), size=size)]}
        return ArchiveJob(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

    def test_verify_true_when_destination_fully_present(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        dest = self.archive_root / "file.txt"
        dest.write_text("hello")  # present, 5 bytes matches manifest size

        storage = StorageDisk(settings=self.settings)
        self.assertTrue(storage.verify(self._archive_for(source, 5)))

    def test_verify_false_when_destination_missing(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        # No destination file written.

        storage = StorageDisk(settings=self.settings)
        self.assertFalse(storage.verify(self._archive_for(source, 5)))

    def test_verify_false_when_destination_size_mismatch(self):
        source = self.local_root / "file.txt"
        source.write_text("hello")
        dest = self.archive_root / "file.txt"
        dest.write_text("hi")  # 2 bytes, manifest says 5

        storage = StorageDisk(settings=self.settings)
        self.assertFalse(storage.verify(self._archive_for(source, 5)))

    def test_verify_false_when_only_some_files_present(self):
        a = self.local_root / "a.txt"
        a.write_text("aaa")
        b = self.local_root / "b.txt"
        b.write_text("bbb")
        (self.archive_root / "a.txt").write_text("aaa")  # only a present

        manifest = {
            "store_files": [
                make_manifest_entry(instance_path=str(a), size=3),
                make_manifest_entry(instance_path=str(b), size=3),
            ]
        }
        archive = ArchiveJob(
            manifest=manifest,
            local_root=str(self.local_root),
            archive_root=str(self.archive_root),
            type="posix",
        )

        storage = StorageDisk(settings=self.settings)
        self.assertFalse(storage.verify(archive))


class TestExtractStub(TestStorageDiskBase):
    def test_extract_is_currently_a_noop_stub(self):
        storage = StorageDisk(settings=self.settings)
        self.assertIsNone(storage.extract(archive_name="a", storage_info={}, outdir=str(self.archive_root)))


if __name__ == "__main__":
    unittest.main()
