# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import json

import pytest
from pydantic import ValidationError

import archivist.settings as settings_module
from archivist.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch):
    """These tests are about config discovery, so start from a clean environment."""

    monkeypatch.delenv("ARCHIVIST_CONFIG_PATH", raising=False)


def test_defaults():
    settings = Settings()

    assert settings.name == "archivist_server"
    assert settings.debug is False
    assert settings.database_driver == "sqlite"
    assert settings.archive_type == "posix"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080


def test_sqlite_database_uri():
    uri = Settings(database_driver="sqlite", database="/tmp/foo.db").sqlalchemy_database_uri

    assert uri.drivername == "sqlite"
    assert uri.database == "/tmp/foo.db"


def test_postgres_database_uri():
    uri = Settings(
        database_driver="postgresql",
        database_user="user",
        database_password="pass",
        database_host="localhost",
        database_port=5432,
        database="archivist",
    ).sqlalchemy_database_uri

    assert uri.render_as_string(hide_password=False) == "postgresql://user:pass@localhost:5432/archivist"


def test_load_from_file(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"name": "my-archivist", "port": 9999}))

    settings = Settings.from_file(config)

    assert settings.name == "my-archivist"
    assert settings.port == 9999


def test_from_file_missing_raises():
    with pytest.raises(FileNotFoundError):
        Settings.from_file("/nonexistent/path/config.json")


def test_get_settings_from_environment_path(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"name": "from-env-config"}))
    monkeypatch.setenv("ARCHIVIST_CONFIG_PATH", str(config))

    assert get_settings().name == "from-env-config"


def test_get_settings_raises_on_an_invalid_config_file(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"port": "not-a-port"}))
    monkeypatch.setenv("ARCHIVIST_CONFIG_PATH", str(config))

    with pytest.raises(ValidationError):
        get_settings()


def test_librarian_callback_config_parses_and_reads_its_password_file(tmp_path):
    """Callback destinations are keyed by librarian_name; passwords come from a file, not the config."""

    password_path = tmp_path / "password.txt"
    password_path.write_text("callback-secret\n")

    settings = Settings(
        librarians={
            "lib-a": {"url": "http://librarian.example/"},
            "lib-b": {
                "url": "http://other.example/",
                "username": "archuser",
                "password_file": str(password_path),
            },
        }
    )

    assert settings.librarians["lib-a"].url == "http://librarian.example/"
    assert settings.librarians["lib-a"].password is None
    assert settings.librarians["lib-b"].password == "callback-secret"


def test_client_config_reads_its_password_file(tmp_path):
    """The password lives in a file both Archivist and the submitting Librarian read."""

    password_path = tmp_path / "password.txt"
    password_path.write_text("shared-secret\n")

    settings = Settings(clients={"lib": {"username": "archuser", "password_file": str(password_path)}})

    assert settings.clients["lib"].password == "shared-secret"


def test_an_enabled_client_without_a_credential_is_rejected():
    with pytest.raises(ValidationError):
        Settings(clients={"lib": {}})


def test_a_client_named_like_the_cli_sentinel_is_allowed():
    """Unlike `librarians`, a sentinel entry here is how the CLI authenticates."""

    settings = Settings(clients={"__cli__": {"username": "cliuser", "password": "t"}})

    assert settings.clients["__cli__"].password == "t"


def test_a_librarian_named_like_the_cli_sentinel_is_rejected():
    """CLI jobs run under the sentinel and never call back; a real librarian must not shadow it."""

    with pytest.raises(ValueError):
        Settings(cli_librarian_name="__cli__", librarians={"__cli__": {"url": "http://x/"}})
