# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
from datetime import datetime, timezone
from unittest import mock

import pytest

import archivist.database as database
import archivist.queue as queue_module
import archivist.settings as settings_module
from archivist.settings import ClientConfig, LibrarianCallbackConfig, Settings
from archivist.storage.storage_disk import StorageDisk

LIBRARIAN_URL = "https://librarian.example.org"

# Distinct per client: a token shared between two entries would make the
# submitter Archivist resolves depend on dict order.
LIBRARIAN_TOKEN = "librarian-token"
CLI_TOKEN = "cli-token"


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
    """A Settings instance backed by a throwaway on-disk sqlite database.

    Callback settings belong here rather than being assigned onto the object
    later: `get_settings()` re-reads the config file on every call and builds
    a fresh Settings, so a mutated instance is invisible to anything that
    calls it again.
    """

    return Settings(
        database_driver="sqlite",
        database=str(tmp_path / "archivist_test.db"),
        archive_type="posix",
        archive_root=str(archive_root),
        local_root=str(local_root),
        librarians={"test-librarian": LibrarianCallbackConfig(url=LIBRARIAN_URL)},
        clients={
            "test-librarian": ClientConfig(auth_token=LIBRARIAN_TOKEN),
            "__cli__": ClientConfig(auth_token=CLI_TOKEN),
        },
        callback_poll_interval_seconds=0.01,  # keep the callback worker's idle wait out of test runtime
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
    id="m1",
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
        manifest_id=id,
        librarian_name=librarian_name,
    )
    manifest.entries = [ManifestEntry(**entry) for entry in entries]
    manifest.total_size_bytes = sum(entry["size"] for entry in entries)
    manifest.file_count = len(entries)

    item = Archive.new_item(manifest=manifest, archive_root=str(archive_root))
    session.add(item)
    session.commit()
    return item


def make_manifest_request(id="m1", json_safe=False, **overrides):
    """A one-entry manifest request body. Set `json_safe=True` for a raw HTTP JSON body.

    `id` is Librarian-minted and doubles as the idempotency key, so
    callers that resubmit (or want distinct manifests) set it explicitly.
    """

    entry = make_manifest_entry(**overrides)
    if json_safe:
        for key in ("create_time", "instance_create_time"):
            entry[key] = entry[key].isoformat()

    return {
        "manifest_id": id,
        "librarian_name": "test-librarian",
        "archive_name": "test-archive",
        "archive_files": [entry],
    }


def make_orphan(session, id, local_root, archive_root, retries=0):
    """Persist an archive job left consumed-but-incomplete, as a crash mid-copy would."""

    source = local_root / f"{id}.txt"
    source.write_text("content")

    item = make_archive_item(
        session,
        id=id,
        archive_root=str(archive_root),
        entries=[make_manifest_entry(instance_path=str(source), size=7)],
    )
    item.consumed = True
    item.retries = retries
    session.commit()
    return item


## -------- Callback fixtures -------------------------------------------------------------


@pytest.fixture
def send():
    """Patch out the outgoing POST and hand back the mock."""

    with mock.patch("archivist.tasks.callback.send_archive_callback") as mock_send:
        yield mock_send


def make_awaiting_callback(
    session,
    archive_root,
    id="m1",
    librarian_name="test-librarian",
    completed_time=None,
    **overrides,
):
    """Persist a completed archive row that still owes its Librarian a report."""

    item = make_archive_item(
        session,
        id=id,
        librarian_name=librarian_name,
        archive_root=str(archive_root),
    )
    item.completed = True
    item.completed_time = completed_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    item.archive_path = str(archive_root)
    item.callback_pending()
    for field, value in overrides.items():
        setattr(item, field, value)
    session.commit()
    return item
