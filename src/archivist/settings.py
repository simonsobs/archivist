import datetime
import os
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """
    Settings for the archivist . Note that because this is a BaseSettings
    object, you can overwrite the values in the config file with environment
    variables.
    """

    # Top level name of the server. Should be unique.
    name: str = "archivist_server"

    # Whether to enable debugging features, like the API docs and OpenAPI schema.
    debug: bool = False

    # Database settings.
    database_driver: str = "sqlite"
    database_user: str | None = None
    database_password: str | None = None
    database_host: str | None = None
    database_port: int | None = None
    database: str | None = None

    database_password_file: Path | None = None

    log_level: str = "DEBUG"

    # Display name and description of the site, used in UI only.
    displayed_site_name: str = "Untitled Archivist Server"
    displayed_site_description: str = "No description set."

    # Host and port to bind to.
    host: str = "0.0.0.0"
    port: int = 8080

    # storage options
    storage_type: str = "posix"
    storage_root: str = "/tmp/archivist_storage"

    # Database migration settings
    alembic_config_path: str = "."
    alembic_path: str = "alembic"

    # Client restraints
    max_search_results: int = 64
    maximal_size_bytes: int = 1_000_000_000_000  # 1 TB

    # Globus integration; by default disable this. This contains a client ID and
    # login secret (for authenticating with Globus as a service), whether this
    # client is a "native app" or not, as well as the UUID for the local Globus
    # endpoint. That endpoint ID should be duplicated in any async transfer manager
    # definitions we want to use a source. We also save the "local root" for the Globus
    # endpoint, which is the root directory presented to the Globus endpoint and
    # all file transfers using Globus are relative to. For example, if the
    # endpoint is configured so that `/mnt/globus` is the local root, then the
    # path to `/mnt/globus/file.txt` should be given as `/~/file.txt`.  This is
    # important for forming paths that Globus can understand.
    globus_enable: bool = False
    globus_client_id: str = ""
    globus_client_native_app: bool = False
    globus_local_endpoint_id: str = ""
    globus_local_root: str | None = None
    globus_encrypt_transfers: bool = True

    globus_client_secret: str | None = None
    globus_client_secret_file: Path | None = None

    # Checksumming options
    checksum_threads: int = 4
    checksum_timeout: datetime.timedelta = datetime.timedelta(days=1)

    def model_post_init(__context, *args, **kwargs):
        """
        Read sensitive data from their appropriate files.
        """

        if __context.globus_client_secret_file is not None:
            with open(__context.globus_client_secret_file, "r") as handle:
                __context.globus_client_secret = handle.read().strip()

        if __context.database_password_file is not None:
            with open(__context.database_password_file, "r") as handle:
                __context.database_password = handle.read().strip()

    @property
    def sqlalchemy_database_uri(self) -> URL:
        """
        The SQLAlchemy database URI.
        """

        return URL.create(
            self.database_driver,
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database,
        )

    @classmethod
    def from_file(cls, config_path: Path | str) -> "Settings":
        """
        Loads the settings from the given path.
        """

        with open(config_path, "r") as handle:
            return cls.model_validate_json(handle.read())


# Automatically create a variable, server_settings, from the environment variable
# on _use_!
_settings = None


def get_settings() -> "Settings":
    """
    Dependency to get the application settings.
    """
    global _settings

    try_paths = [
        os.environ.get("LIBRARIAN_CONFIG_PATH", None),
    ]

    for path in try_paths:
        if path is not None:
            path = Path(path)
        else:
            continue

        if path.exists():
            try:
                _settings = Settings.from_file(path)
            except ValidationError as e:
                print(f"Error loading settings from {path}: {e}")
                raise e

            return _settings
    try:
        _settings = Settings()
    except ValidationError as e:
        print(f"Not all settings have defaults: {e}")
        raise e

    return _settings
