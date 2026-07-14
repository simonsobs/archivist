# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.core.archive.Archive."""

import unittest
from pathlib import Path

from conftest import make_manifest_entry

from archivist.core.archive_job import ArchiveJob


class TestArchiveProperties(unittest.TestCase):
    def test_defaults_are_none(self):
        archive = ArchiveJob()
        self.assertIsNone(archive.manifest)
        self.assertIsNone(archive.manifest_id)
        self.assertIsNone(archive.local_root)
        self.assertIsNone(archive.archive_root)
        self.assertIsNone(archive.checksum)

    def test_constructor_sets_properties(self):
        manifest = {"store_files": []}
        archive = ArchiveJob(
            manifest=manifest,
            manifest_id="abc",
            local_root="/local",
            archive_root="/archive",
            type="posix",
        )
        self.assertEqual(archive.manifest, manifest)
        self.assertEqual(archive.manifest_id, "abc")
        self.assertEqual(archive.local_root, "/local")
        self.assertEqual(archive.archive_root, "/archive")

    def test_repr_includes_key_fields(self):
        archive = ArchiveJob(manifest_id="abc", type="posix")
        text = repr(archive)
        self.assertIn("abc", text)
        self.assertIn("posix", text)


class TestCreateArchivePosix(unittest.TestCase):
    def test_builds_src_dst_pairs_relative_to_local_root(self):
        manifest = {
            "store_files": [
                make_manifest_entry(instance_path="/local/sub/file.txt", size=4096),
            ]
        }
        archive = ArchiveJob(
            manifest=manifest,
            local_root="/local",
            archive_root="/archive",
            type="posix",
        )

        pairs = archive.create_archive()

        self.assertEqual(len(pairs), 1)
        src, dst, size = pairs[0]
        self.assertEqual(src, Path("/local/sub/file.txt"))
        self.assertEqual(dst, Path("/archive/sub/file.txt"))
        self.assertEqual(size, 4096)

    def test_multiple_entries_preserve_order(self):
        manifest = {
            "store_files": [
                make_manifest_entry(instance_path="/local/a.txt"),
                make_manifest_entry(instance_path="/local/b.txt"),
            ]
        }
        archive = ArchiveJob(manifest=manifest, local_root="/local", archive_root="/archive", type="posix")

        pairs = archive.create_archive()

        self.assertEqual([str(src) for src, _, _ in pairs], ["/local/a.txt", "/local/b.txt"])

    def test_includes_manifest_size_per_entry(self):
        manifest = {
            "store_files": [
                make_manifest_entry(instance_path="/local/a.txt", size=10),
                make_manifest_entry(instance_path="/local/b.txt", size=20),
            ]
        }
        archive = ArchiveJob(manifest=manifest, local_root="/local", archive_root="/archive", type="posix")

        pairs = archive.create_archive()

        self.assertEqual([size for _, _, size in pairs], [10, 20])

    def test_empty_store_files_returns_empty_list(self):
        archive = ArchiveJob(manifest={"store_files": []}, local_root="/local", archive_root="/archive", type="posix")
        self.assertEqual(archive.create_archive(), [])


class TestCreateArchiveOtherTypes(unittest.TestCase):
    def test_hpss_returns_none(self):
        archive = ArchiveJob(manifest={"store_files": []}, type="hpss")
        self.assertIsNone(archive.create_archive())

    def test_unknown_type_returns_none(self):
        archive = ArchiveJob(manifest={"store_files": []}, type="something-else")
        self.assertIsNone(archive.create_archive())


if __name__ == "__main__":
    unittest.main()
