# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
"""Shared pytest fixtures for the archivist test suite."""

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

    db_path = tmp_path / "archivist_test.db"
    return Settings(
        database_driver="sqlite",
        database=str(db_path),
        archive_type="posix",
        archive_root=str(archive_root),
        local_root=str(local_root),
    )


@pytest.fixture
def use_settings(monkeypatch, settings, tmp_path):
    """
    Make `get_settings()` return `settings`, regardless of whether the
    caller does `import archivist.settings` or
    `from archivist.settings import get_settings` (the latter binds its
    own reference, so patching the module attribute alone would miss it).
    We instead drive this through the same env-var + cache mechanism
    `get_settings()` itself uses.
    """

    config_path = tmp_path / "test_config.json"
    config_path.write_text(settings.model_dump_json())

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

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry = dict(
        name="file.txt",
        create_time=now,
        size=1024,
        checksum="0" * 64,
        uploader="test-uploader",
        source="/source",
        instance_path="/source/file.txt",
        instance_create_time=now,
        instance_available=True,
        outgoing_transfer_id=0,
    )
    entry.update(overrides)
    return entry


def make_manifest_entry_json(**overrides):
    """Like `make_manifest_entry`, but with datetimes as ISO strings for use as raw HTTP JSON bodies."""

    entry = make_manifest_entry(**overrides)
    for key in ("create_time", "instance_create_time"):
        if isinstance(entry[key], datetime):
            entry[key] = entry[key].isoformat()
    return entry


@pytest.fixture
def manifest_entry_data():
    return make_manifest_entry()


@pytest.fixture
def manifest_request_data(manifest_entry_data):
    return {
        "librarian_name": "test-librarian",
        "store_files": [manifest_entry_data],
    }
