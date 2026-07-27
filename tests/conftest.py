# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
from datetime import datetime, timezone

import pytest

import archivist.database as database
import archivist.queue as queue_module
import archivist.settings as settings_module
from archivist.settings import Settings
from archivist.storage.storage_disk import StorageDisk


@pytest.fixture(autouse=True)
def _reset_module_singletons():
    """
    Several modules cache lazily-created global state (the DB engine,
    session maker, loaded settings, the in-memory status queue, and the
    shared StorageDisk thread pool). Reset all of it before and after
    every test so tests don't leak state into one another.
    """

    def _reset():
        if database._engine is not None:
            database._engine.dispose()
        database._engine = None
        database._SessionMaker = None
        settings_module._settings = None
        queue_module._status_queue = None
        StorageDisk._executor = None

    _reset()
    yield
    _reset()


@pytest.fixture
def archive_root(tmp_path):
    path = tmp_path / "archive_root"
    path.mkdir()
    return path


@pytest.fixture
def local_root(tmp_path):
    path = tmp_path / "local_root"
    path.mkdir()
    return path


@pytest.fixture
def settings(tmp_path, archive_root, local_root) -> Settings:
    """A Settings instance backed by a throwaway on-disk sqlite database."""

    return Settings(
        database_driver="sqlite",
        database=str(tmp_path / "archivist_test.db"),
        archive_type="posix",
        archive_root=str(archive_root),
        local_root=str(local_root),
    )


@pytest.fixture
def config_path(settings, tmp_path):
    """`settings` serialised to a JSON file, as the CLI/server would be given."""

    path = tmp_path / "test_config.json"
    path.write_text(settings.model_dump_json())
    return path


@pytest.fixture
def use_settings(monkeypatch, settings, config_path):
    """
    Make `get_settings()` return `settings`, regardless of whether the
    caller does `import archivist.settings` or
    `from archivist.settings import get_settings` (the latter binds its
    own reference, so patching the module attribute alone would miss it).
    We instead drive this through the same env-var + cache mechanism
    `get_settings()` itself uses.
    """

    monkeypatch.setenv("ARCHIVIST_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(settings_module, "_settings", None)

    return settings_module.get_settings()


@pytest.fixture
def db_session(use_settings):
    """A real database session against a freshly created schema."""

    database.create_all()
    session = database.get_session()
    try:
        yield session
    finally:
        session.close()


def make_manifest_entry(**overrides):
    """Build a dict-form manifest entry, suitable for `ManifestEntry(**entry)`."""

    entry = {
        "name": "file.txt",
        "create_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "size": 1024,
        "checksum": "0" * 64,
        "uploader": "test-uploader",
        "source": "/source",
        "instance_path": "/source/file.txt",
        "instance_create_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "instance_available": True,
        "outgoing_transfer_id": 0,
    }
    entry.update(overrides)
    return entry


def make_archive_item(
    session,
    manifest_id="m1",
    *,
    librarian_name="test-librarian",
    archive_root="/root",
    entries=None,
):
    """Persist a `Manifest` (+ `ManifestEntry` rows) and its `Archive` job.

    Mirrors what the `/archive` route does, so worker/ORM tests can build a
    ready-to-dequeue job in one call. `entries` is a list of dicts as produced
    by `make_manifest_entry`; defaults to a single entry.
    """

    from archivist.orm import Archive, Manifest, ManifestEntry

    if entries is None:
        entries = [make_manifest_entry()]

    manifest = Manifest.get_or_create(
        session,
        manifest_id=manifest_id,
        librarian_name=librarian_name,
    )
    manifest.entries = [ManifestEntry(**entry) for entry in entries]
    manifest.total_size_bytes = sum(entry["size"] for entry in entries)
    manifest.file_count = len(entries)

    item = Archive.new_item(manifest=manifest, archive_root=str(archive_root))
    session.add(item)
    session.commit()
    return item


def make_manifest_request(json_safe=False, **overrides):
    """A one-entry manifest request body. Set `json_safe=True` for a raw HTTP JSON body."""

    entry = make_manifest_entry(**overrides)
    if json_safe:
        for key in ("create_time", "instance_create_time"):
            entry[key] = entry[key].isoformat()

    return {"librarian_name": "test-librarian", "store_files": [entry]}
