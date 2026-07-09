# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.settings.Settings and get_settings()."""

import json
import unittest
import unittest.mock

import archivist.settings as settings_module
from archivist.settings import Settings, get_settings


class TestSettingsDefaults(unittest.TestCase):
    def test_defaults(self):
        settings = Settings()
        self.assertEqual(settings.name, "archivist_server")
        self.assertFalse(settings.debug)
        self.assertEqual(settings.database_driver, "sqlite")
        self.assertEqual(settings.archive_type, "posix")
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 8080)


class TestSqlalchemyDatabaseUri(unittest.TestCase):
    def test_sqlite_uri(self):
        settings = Settings(database_driver="sqlite", database="/tmp/foo.db")
        uri = settings.sqlalchemy_database_uri
        self.assertEqual(uri.drivername, "sqlite")
        self.assertEqual(uri.database, "/tmp/foo.db")

    def test_postgres_uri_includes_credentials(self):
        settings = Settings(
            database_driver="postgresql",
            database_user="user",
            database_password="pass",
            database_host="localhost",
            database_port=5432,
            database="archivist",
        )
        uri = settings.sqlalchemy_database_uri
        self.assertEqual(uri.drivername, "postgresql")
        self.assertEqual(uri.username, "user")
        self.assertEqual(uri.password, "pass")
        self.assertEqual(uri.host, "localhost")
        self.assertEqual(uri.port, 5432)
        self.assertEqual(uri.database, "archivist")


class TestFromFile(unittest.TestCase):
    def test_from_file_loads_values(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(json.dumps({"name": "my-archivist", "port": 9999}))

            settings = Settings.from_file(config_path)

            self.assertEqual(settings.name, "my-archivist")
            self.assertEqual(settings.port, 9999)

    def test_from_file_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            Settings.from_file("/nonexistent/path/config.json")


class TestSecretFiles(unittest.TestCase):
    def test_globus_client_secret_read_from_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            secret_path = Path(tmp_dir) / "secret.txt"
            secret_path.write_text("super-secret\n")

            settings = Settings(globus_client_secret_file=secret_path)

            self.assertEqual(settings.globus_client_secret, "super-secret")

    def test_database_password_read_from_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            secret_path = Path(tmp_dir) / "dbpass.txt"
            secret_path.write_text("db-secret\n")

            settings = Settings(database_password_file=secret_path)

            self.assertEqual(settings.database_password, "db-secret")


class TestGetSettings(unittest.TestCase):
    def setUp(self):
        self._original = settings_module._settings
        settings_module._settings = None

    def tearDown(self):
        settings_module._settings = self._original

    def test_get_settings_from_env_config_path(self):
        import tempfile
        from pathlib import Path

        from pytest import MonkeyPatch

        mp = MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = Path(tmp_dir) / "config.json"
                config_path.write_text(json.dumps({"name": "from-env-config"}))

                mp.setenv("ARCHIVIST_CONFIG_PATH", str(config_path))

                settings = get_settings()

                self.assertEqual(settings.name, "from-env-config")
        finally:
            mp.undo()

    def test_get_settings_falls_back_to_defaults(self):
        from pytest import MonkeyPatch

        mp = MonkeyPatch()
        try:
            mp.delenv("ARCHIVIST_CONFIG_PATH", raising=False)

            settings = get_settings()

            self.assertEqual(settings.name, "archivist_server")
        finally:
            mp.undo()

    def test_server_settings_attribute_lazily_loads(self):
        from pytest import MonkeyPatch

        mp = MonkeyPatch()
        try:
            mp.delenv("ARCHIVIST_CONFIG_PATH", raising=False)

            self.assertIsInstance(settings_module.server_settings, Settings)
        finally:
            mp.undo()

    def test_unknown_attribute_raises(self):
        with self.assertRaises(AttributeError):
            settings_module.not_a_real_attribute

    def test_server_settings_returns_already_loaded_settings(self):
        sentinel = Settings(name="already-loaded")
        settings_module._settings = sentinel

        self.assertIs(settings_module.server_settings, sentinel)

    def test_get_settings_from_file_with_invalid_content_raises(self):
        import tempfile
        from pathlib import Path

        from pydantic import ValidationError
        from pytest import MonkeyPatch

        mp = MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = Path(tmp_dir) / "config.json"
                config_path.write_text(json.dumps({"port": "not-a-port"}))

                mp.setenv("ARCHIVIST_CONFIG_PATH", str(config_path))

                with self.assertRaises(ValidationError):
                    get_settings()
        finally:
            mp.undo()

    def test_get_settings_default_construction_error_is_reraised(self):
        from pydantic import BaseModel, ValidationError
        from pytest import MonkeyPatch

        class _RequiresField(BaseModel):
            required: int

        try:
            _RequiresField()
        except ValidationError as captured:
            validation_error = captured

        mp = MonkeyPatch()
        try:
            mp.delenv("ARCHIVIST_CONFIG_PATH", raising=False)
            mp.setattr(settings_module, "Settings", unittest.mock.Mock(side_effect=validation_error))

            with self.assertRaises(ValidationError):
                get_settings()
        finally:
            mp.undo()


if __name__ == "__main__":
    unittest.main()
