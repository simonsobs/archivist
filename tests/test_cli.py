# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""
Tests for the archivist.__main__ click CLI.

The only real logic here is turning a source path into a manifest; the rest
is click/requests plumbing, so that's all this covers.
"""

import hashlib
import os
from unittest import mock

import pytest
from click.testing import CliRunner

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
    response.json.return_value = {"manifest_id": "abc-123"}

    with mock.patch.object(cli_module.requests, "post", return_value=response) as mock_post:
        yield mock_post


@pytest.mark.parametrize("source_is_dir", [False, True], ids=["single-file", "directory"])
def test_archive_builds_a_manifest_from_the_source_path(config_path, post, tmp_path, source_is_dir):
    """A directory is walked recursively; a file is archived on its own."""

    source_dir = tmp_path / "adir"
    (source_dir / "sub").mkdir(parents=True)
    (source_dir / "a.txt").write_bytes(b"a")
    (source_dir / "sub" / "b.txt").write_bytes(b"b")

    source = source_dir if source_is_dir else source_dir / "a.txt"
    expected_names = ["a.txt", "b.txt"] if source_is_dir else ["a.txt"]

    result = CliRunner().invoke(main, ["-c", str(config_path), "archive", "--source-path", str(source)])

    assert result.exit_code == 0
    assert "Archive succeeded, manifest_id=abc-123" in result.output

    body = post.call_args.kwargs["json"]
    assert body["librarian_name"] == "librarian"
    assert sorted(entry["name"] for entry in body["store_files"]) == expected_names

    entry = next(entry for entry in body["store_files"] if entry["name"] == "a.txt")
    assert entry["checksum"] == hashlib.sha256(b"a").hexdigest()


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
