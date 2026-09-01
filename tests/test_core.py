# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import hashlib
from pathlib import Path

import pytest
from conftest import make_manifest_entry
from pydantic import ValidationError

from archivist.core.archive_job import ArchiveJob
from archivist.core.models import ManifestEntry, ManifestRequest
from archivist.utils import _checksum


@pytest.mark.parametrize(
    "data", [b"", b"hello world", b"x" * (1024 * 1024 + 17)], ids=["empty", "small", "multi-chunk"]
)
def test_checksum(tmp_path, data):
    path = tmp_path / "file.bin"
    path.write_bytes(data)

    assert _checksum(str(path)) == hashlib.sha256(data).hexdigest()


def test_manifest_request_accepts_many_or_no_entries():
    request = ManifestRequest(
        manifest_id="m1",
        librarian_name="lib",
        archive_files=[make_manifest_entry(), make_manifest_entry(name="other.txt")],
    )

    assert request.librarian_name == "lib"
    assert len(request.archive_files) == 2
    assert isinstance(request.archive_files[0], ManifestEntry)
    assert isinstance(request.archive_files[1], ManifestEntry)
    empty = ManifestRequest(manifest_id="m1", librarian_name="lib", archive_files=[])
    assert empty.archive_files == []

    # Both `manifest_id` and `librarian_name` are required.
    with pytest.raises(ValidationError):
        ManifestRequest(archive_files=[])


def test_archive_construction():
    archive = ArchiveJob()

    assert archive.manifest is None
    assert archive.manifest_id is None
    assert archive.local_root is None
    assert archive.archive_root is None
    assert archive.checksum is None

    manifest = {"store_files": []}
    archive = ArchiveJob(
        manifest=manifest,
        manifest_id="abc",
        local_root="/local",
        archive_root="/archive",
        type="posix",
    )

    assert archive.manifest == manifest
    assert archive.manifest_id == "abc"
    assert archive.local_root == "/local"
    assert archive.archive_root == "/archive"
    assert "abc" in repr(archive)
    assert "posix" in repr(archive)


def test_create_archive_posix():
    """The source/destination pairs are what a storage backend actually copies."""

    manifest = {
        "store_files": [
            make_manifest_entry(instance_path="/local/sub/file.txt"),
            make_manifest_entry(instance_path="/local/b.txt"),
        ]
    }
    archive = ArchiveJob(manifest=manifest, local_root="/local", archive_root="/archive", type="posix")

    pairs = archive.create_archive()

    assert pairs == [
        (Path("/local/sub/file.txt"), Path("/archive/sub/file.txt"), 1024),
        (Path("/local/b.txt"), Path("/archive/b.txt"), 1024),
    ]


@pytest.mark.parametrize("archive_type", ["hpss", "something-else"])
def test_create_archive_returns_none_for_unsupported_types(archive_type):
    assert ArchiveJob(manifest={"store_files": []}, type=archive_type).create_archive() is None
