# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for the archivist.__main__ click CLI."""

import os
import unittest
import unittest.mock
from pathlib import Path

import pytest
import requests
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
def cli_config_path(settings, tmp_path):
    config_path = tmp_path / "cli_config.json"
    config_path.write_text(settings.model_dump_json())
    return str(config_path)


@pytest.fixture
def runner():
    return CliRunner()


class TestMainRequiresConfig(unittest.TestCase):
    def test_missing_config_exits_1(self):
        runner = CliRunner()
        result = runner.invoke(main, ["archive", "--source-path", "."])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("requires a configuration file", result.output)

    def test_nonexistent_config_is_a_usage_error(self):
        runner = CliRunner()
        result = runner.invoke(main, ["-c", "/no/such/config.json", "archive", "--source-path", "."])

        self.assertEqual(result.exit_code, 2)


class TestArchiveCommand:
    def test_archive_single_file_success(self, runner, cli_config_path, settings):
        # The CLI names files by their path relative to settings.local_root,
        # so sources must live under it.
        source = Path(settings.local_root) / "file.txt"
        source.write_text("hello world")

        fake_response = unittest.mock.Mock(status_code=200)
        fake_response.json.return_value = {"manifest_id": "abc-123"}

        with unittest.mock.patch.object(cli_module.requests, "post", return_value=fake_response) as mock_post:
            result = runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", str(source)])

        assert result.exit_code == 0
        assert "Archive succeeded, manifest_id=abc-123" in result.output

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        # No --librarian-name given, so the job runs under the reserved CLI
        # sentinel and will never trigger a Librarian callback.
        assert body["librarian_name"] == settings.cli_librarian_name
        assert len(body["store_files"]) == 1
        assert body["store_files"][0]["name"] == "file.txt"

    def test_archive_computes_correct_checksum(self, runner, cli_config_path, settings):
        import hashlib

        source = Path(settings.local_root) / "file.txt"
        source.write_bytes(b"some content to checksum")

        fake_response = unittest.mock.Mock(status_code=200)
        fake_response.json.return_value = {"manifest_id": "abc-123"}

        with unittest.mock.patch.object(cli_module.requests, "post", return_value=fake_response) as mock_post:
            runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", str(source)])

        _, kwargs = mock_post.call_args
        expected = hashlib.sha256(b"some content to checksum").hexdigest()
        assert kwargs["json"]["store_files"][0]["checksum"] == expected

    def test_archive_directory_walks_all_files(self, runner, cli_config_path, settings):
        source_dir = Path(settings.local_root) / "adir"
        (source_dir / "sub").mkdir(parents=True)
        (source_dir / "a.txt").write_text("a")
        (source_dir / "sub" / "b.txt").write_text("b")

        fake_response = unittest.mock.Mock(status_code=200)
        fake_response.json.return_value = {"manifest_id": "abc-123"}

        with unittest.mock.patch.object(cli_module.requests, "post", return_value=fake_response) as mock_post:
            result = runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", str(source_dir)])

        assert result.exit_code == 0
        _, kwargs = mock_post.call_args
        names = sorted(entry["name"] for entry in kwargs["json"]["store_files"])
        # Names are paths relative to settings.local_root, preserving the full
        # subdirectory structure rather than bare basenames.
        assert names == ["adir/a.txt", "adir/sub/b.txt"]

    def test_archive_uses_custom_librarian_name(self, runner, cli_config_path, settings):
        source = Path(settings.local_root) / "file.txt"
        source.write_text("hello")

        fake_response = unittest.mock.Mock(status_code=200)
        fake_response.json.return_value = {"manifest_id": "abc-123"}

        with unittest.mock.patch.object(cli_module.requests, "post", return_value=fake_response) as mock_post:
            runner.invoke(
                main,
                [
                    "-c",
                    cli_config_path,
                    "archive",
                    "--source-path",
                    str(source),
                    "--librarian-name",
                    "custom-librarian",
                ],
            )

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["librarian_name"] == "custom-librarian"
        assert kwargs["json"]["store_files"][0]["uploader"] == "custom-librarian"

    def test_archive_server_error_prints_error_and_exits_cleanly(self, runner, cli_config_path, settings):
        source = Path(settings.local_root) / "file.txt"
        source.write_text("hello")

        fake_response = unittest.mock.Mock(status_code=400)
        fake_response.json.return_value = {"error": "too big"}

        with unittest.mock.patch.object(cli_module.requests, "post", return_value=fake_response):
            result = runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", str(source)])

        assert result.exit_code == 0
        assert "Archive failed: too big" in result.output

    def test_archive_connection_error_propagates(self, runner, cli_config_path, settings):
        source = Path(settings.local_root) / "file.txt"
        source.write_text("hello")

        with unittest.mock.patch.object(
            cli_module.requests, "post", side_effect=requests.exceptions.ConnectionError("no server")
        ):
            result = runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", str(source)])

        assert result.exit_code != 0
        assert isinstance(result.exception, requests.exceptions.ConnectionError)

    def test_archive_missing_source_path_is_usage_error(self, runner, cli_config_path):
        result = runner.invoke(main, ["-c", cli_config_path, "archive", "--source-path", "/no/such/file"])

        assert result.exit_code == 2


class TestExtractCommand:
    def test_extract_command_currently_raises_type_error(self, runner, cli_config_path):
        """
        `extract()`'s signature is `(ctx, archive, dest_path)`, but the command
        declares `@click.argument("cmd")`, which click passes as a `cmd` kwarg
        the function doesn't accept. This documents the current, broken
        behavior rather than asserting the (not-yet-implemented) command works.
        """
        result = runner.invoke(
            main,
            ["-c", cli_config_path, "extract", "cmd", "--archive", "foo", "--dest-path", "/tmp/out"],
        )

        assert result.exit_code != 0
        assert isinstance(result.exception, TypeError)


class TestResendCallbackCommand:
    @staticmethod
    def _make_completed_archive(db_session, archive_root, *, callback_state, attempts, completed=True):
        from datetime import datetime, timezone

        from conftest import make_archive_item

        item = make_archive_item(db_session, manifest_id="m1", archive_root=str(archive_root))
        item.completed = completed
        item.completed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        item.callback_state = callback_state
        item.callback_attempts = attempts
        item.callback_last_error = "boom"
        db_session.commit()
        return item

    def test_resets_an_exhausted_callback_to_pending(self, runner, cli_config_path, db_session, archive_root):
        from archivist.orm.archive import Archive

        self._make_completed_archive(db_session, archive_root, callback_state="exhausted", attempts=5)

        result = runner.invoke(main, ["-c", cli_config_path, "resend-callback", "--manifest-id", "m1"])

        assert result.exit_code == 0
        assert "reset to pending" in result.output

        db_session.expire_all()
        item = db_session.query(Archive).filter_by(manifest_id="m1").one()
        assert item.callback_state == "pending"
        assert item.callback_attempts == 0
        assert item.callback_next_retry is not None
        assert item.callback_last_error is None

    def test_unknown_manifest_reports_an_error(self, runner, cli_config_path, db_session):
        result = runner.invoke(main, ["-c", cli_config_path, "resend-callback", "--manifest-id", "nope"])

        assert result.exit_code == 0
        assert "No completed archive for manifest nope" in result.output

    def test_incomplete_archive_is_not_reset(self, runner, cli_config_path, db_session, archive_root):
        from archivist.orm.archive import Archive

        self._make_completed_archive(db_session, archive_root, callback_state="pending", attempts=0, completed=False)

        result = runner.invoke(main, ["-c", cli_config_path, "resend-callback", "--manifest-id", "m1"])

        assert result.exit_code == 0
        assert "No completed archive for manifest m1" in result.output

        db_session.expire_all()
        item = db_session.query(Archive).filter_by(manifest_id="m1").one()
        assert item.callback_next_retry is None

    def test_manifest_id_is_required(self, runner, cli_config_path):
        result = runner.invoke(main, ["-c", cli_config_path, "resend-callback"])

        assert result.exit_code == 2


class TestStartServerCommand:
    def test_start_server_invokes_uvicorn_with_settings(self, runner, cli_config_path, settings):
        with unittest.mock.patch("uvicorn.run") as mock_run:
            result = runner.invoke(main, ["-c", cli_config_path, "start-server"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            "archivist.server:main",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            factory=True,
        )


if __name__ == "__main__":
    unittest.main()
