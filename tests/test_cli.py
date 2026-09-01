# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""
Tests for the archivist.__main__ click CLI.

The only real logic here is turning a source path into a manifest; the rest
is click/requests plumbing, so that's all this covers.
"""

import hashlib
import os
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from conftest import CLI_CREDENTIALS, make_archive_item

import archivist.__main__ as cli_module
from archivist.__main__ import main


@pytest.fixture(autouse=True)
def _restore_config_path_env():
    """
    The CLI's `main()` callback mutates `os.environ` directly (not via
    click/pydantic-settings helpers), so make sure it doesn't leak the path
    to a tmp_path config file that gets torn down after this test into
    later, unrelated tests.
    """

    original = os.environ.get("ARCHIVIST_CONFIG_PATH")
    yield
    if original is None:
        os.environ.pop("ARCHIVIST_CONFIG_PATH", None)
    else:
        os.environ["ARCHIVIST_CONFIG_PATH"] = original


@pytest.fixture
def post():
    """Patch out the HTTP call to the server and hand back the mock."""

    response = mock.Mock(status_code=200)
    response.json.return_value = {"manifest_id": "abc-123", "archive_id": "abc-123"}

    with mock.patch.object(cli_module.requests, "post", return_value=response) as mock_post:
        yield mock_post


@pytest.mark.parametrize("source_is_dir", [False, True], ids=["single-file", "directory"])
def test_archive_builds_a_manifest_from_the_source_path(config_path, post, settings, source_is_dir):
    """A directory is walked recursively; a file is archived on its own."""

    # Entries are named by their path relative to settings.local_root, so
    # sources have to live under it.
    source_dir = Path(settings.local_root) / "adir"
    (source_dir / "sub").mkdir(parents=True)
    (source_dir / "a.txt").write_bytes(b"a")
    (source_dir / "sub" / "b.txt").write_bytes(b"b")

    source = source_dir if source_is_dir else source_dir / "a.txt"
    expected_names = ["adir/a.txt", "adir/sub/b.txt"] if source_is_dir else ["adir/a.txt"]

    result = CliRunner().invoke(main, ["-c", str(config_path), "archive", "--source-path", str(source)])

    assert result.exit_code == 0
    assert "Archive succeeded, manifest_id=abc-123" in result.output

    body = post.call_args.kwargs["json"]
    # No --librarian-name given, so the job runs under the reserved CLI
    # sentinel and will never trigger a Librarian callback.
    assert body["librarian_name"] == settings.cli_librarian_name
    assert sorted(entry["name"] for entry in body["archive_files"]) == expected_names

    entry = next(entry for entry in body["archive_files"] if entry["name"] == "adir/a.txt")
    assert entry["checksum"] == hashlib.sha256(b"a").hexdigest()


def test_archive_sends_the_credentials_filed_under_the_submitting_name(config_path, post, settings):
    source = Path(settings.local_root) / "file.txt"
    source.write_text("hello")

    result = CliRunner().invoke(main, ["-c", str(config_path), "archive", "--source-path", str(source)])

    assert result.exit_code == 0
    assert post.call_args.kwargs["auth"] == CLI_CREDENTIALS


def test_archive_fails_early_when_the_submitting_name_has_no_credentials(config_path, post, settings):
    """Fails before walking the source tree, with a message naming the fix."""

    source = Path(settings.local_root) / "file.txt"
    source.write_text("hello")

    result = CliRunner().invoke(
        main,
        ["-c", str(config_path), "archive", "--source-path", str(source), "--librarian-name", "unconfigured"],
    )

    assert result.exit_code == 1
    assert "clients" in result.output
    post.assert_not_called()


def test_archive_under_a_named_librarian_is_attributed_to_it(config_path, post, settings):
    """Naming a librarian opts the job into a callback, and sets the uploader."""

    source = Path(settings.local_root) / "file.txt"
    source.write_text("hello")

    result = CliRunner().invoke(
        main,
        ["-c", str(config_path), "archive", "--source-path", str(source), "--librarian-name", "test-librarian"],
    )

    assert result.exit_code == 0
    body = post.call_args.kwargs["json"]
    assert body["librarian_name"] == "test-librarian"
    assert body["archive_files"][0]["uploader"] == "test-librarian"


def test_resend_callback_resets_an_exhausted_callback_to_pending(config_path, db_session, archive_root):
    """Operator escape hatch after fixing a Librarian's config; runs against the DB, not the server."""

    item = make_archive_item(db_session, id="m1", archive_root=str(archive_root))
    item.completed = True
    item.callback_state = "exhausted"
    item.callback_attempts = 5
    item.callback_last_error = "boom"
    db_session.commit()

    result = CliRunner().invoke(main, ["-c", str(config_path), "resend-callback", "--manifest-id", "m1"])

    assert result.exit_code == 0
    assert "reset to pending" in result.output

    db_session.expire_all()
    assert item.callback_state == "pending"
    assert item.callback_attempts == 0
    assert item.callback_last_error is None
    assert item.callback_next_retry is not None


@pytest.mark.parametrize(
    "manifest_id,completed",
    [("nope", None), ("m1", False)],
    ids=["unknown-manifest", "still-in-flight"],
)
def test_resend_callback_only_touches_completed_archives(config_path, db_session, archive_root, manifest_id, completed):
    """Resending a callback for a job that never finished would report a lie."""

    if completed is not None:
        item = make_archive_item(db_session, id="m1", archive_root=str(archive_root))
        item.completed = completed
        db_session.commit()

    result = CliRunner().invoke(main, ["-c", str(config_path), "resend-callback", "--manifest-id", manifest_id])

    assert result.exit_code == 0
    assert f"No completed archive for manifest {manifest_id}" in result.output

    if completed is not None:
        db_session.expire_all()
        assert item.callback_next_retry is None


def test_start_server_hands_the_settings_to_uvicorn(config_path, settings):
    with mock.patch("uvicorn.run") as mock_run:
        result = CliRunner().invoke(main, ["-c", str(config_path), "start-server"])

    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "archivist.server:main",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        factory=True,
    )
