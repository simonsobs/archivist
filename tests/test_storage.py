# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import pytest
from conftest import make_manifest_entry

from archivist.core.archive_job import ArchiveJob
from archivist.storage import storage_factory
from archivist.storage.base import Storage
from archivist.storage.storage_disk import StorageDisk


def _archive_for(source, local_root, archive_root):
    return ArchiveJob(
        manifest={"store_files": [make_manifest_entry(instance_path=str(source))]},
        local_root=str(local_root),
        archive_root=str(archive_root),
        type="posix",
    )


def test_base_storage_notimplemented():
    storage = Storage()

    with pytest.raises(NotImplementedError):
        storage.store(archive=None)

    with pytest.raises(NotImplementedError):
        storage.extract(archive_name="a", storage_info={}, outdir="/tmp/out")


def test_store_returns_the_backend_result_verbatim():
    """`tasks.archive` enqueues whatever `store()` hands back, so it must not be wrapped."""

    sentinel = object()

    class _RecordingStorage(Storage):
        def _store(self, archive):
            self.stored = archive
            return sentinel

    storage = _RecordingStorage()

    assert storage.store(archive="my-archive") is sentinel
    assert storage.stored == "my-archive"


def test_storage_factory_maps_configured_types():
    assert storage_factory["posix"] is StorageDisk


@pytest.mark.parametrize(
    "relative_path",
    ["file.txt", "sub/dir/nested.txt"],
    ids=["top-level", "nested"],
)
def test_disk_store_archive(use_settings, local_root, archive_root, relative_path):
    source = local_root / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("content")

    storage = StorageDisk(settings=use_settings)
    task = storage.store(_archive_for(source, local_root, archive_root))
    task.future.result(timeout=5)

    # `store()` returns the backend itself, carrying the archive and its future.
    assert task is storage
    assert (archive_root / relative_path).read_text() == "content"


def test_disk_store_archive_directory_trees(use_settings, local_root, archive_root):
    source_dir = local_root / "adir"
    source_dir.mkdir()
    (source_dir / "inner.txt").write_text("inner-content")

    storage = StorageDisk(settings=use_settings)
    storage.store(_archive_for(source_dir, local_root, archive_root)).future.result(timeout=5)

    assert (archive_root / "adir" / "inner.txt").read_text() == "inner-content"
