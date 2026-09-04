import datetime
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError, model_validator
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class LibrarianCallbackConfig(BaseModel):
    # Base URL of the Librarian; the callback path is appended to this.
    url: str

    # Presented as HTTP Basic when reporting a completed archive. The
    # Librarian verifies it against the `authenticator` on its own row for
    # this Archivist.
    username: str | None = None
    password: str | None = None
    password_file: Path | None = None


class ClientConfig(BaseModel):
    """
    A Librarian permitted to submit manifests to this Archivist.

    The inbound counterpart to `LibrarianCallbackConfig`: that one is the
    credential Archivist *presents* when reporting a completed archive, this
    one is the credential Archivist *accepts* when work is submitted to it.
    For a Librarian peer the two are deliberately the *same* pair: the
    Librarian keeps a single `archivists.authenticator` row and uses it in
    both directions, so there is one credential to provision and nothing to
    keep in sync.

    The username is the username half of that authenticator, not the
    Librarian's name; the key this config is filed under is the identity
    Archivist resolves a submission to, and the one it checks the manifest's
    `librarian_name` against. Two clients sharing a pair makes that
    resolution ambiguous, so keep them distinct.
    """

    # Credentials this client presents as HTTP Basic.
    username: str | None = None
    password: str | None = None
    password_file: Path | None = None

    # Lets a peer be turned off without dropping its config -- and its
    # password file path -- out of the deployment.
    enabled: bool = True

    @model_validator(mode="after")
    def _credential_present(self) -> "ClientConfig":
        if self.enabled and (self.username is None or (self.password is None and self.password_file is None)):
            raise ValueError("An enabled client needs a username and a password or password_file.")
        return self


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
    archive_type: str = "posix"
    archive_root: str = "/tmp/archivist_storage"
    local_root: str = "/tmp/archivist_local"
    max_archive_retries: int = 3

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

    # Number of background threads used to perform filesystem storage copies.
    # This sizes the pool that runs whole archive *jobs*, not the files within
    # one job -- see copy_threads for that.
    storage_threads: int = 4

    # Concurrent file copies within a single archive job. Copying to network
    # storage is latency-bound rather than bandwidth-bound: each file costs a
    # round trip to open, write, commit and stat, and a single stream spends
    # most of its time waiting. Concurrent streams hide that latency. Set to 1
    # for serial copying, which is the right choice for local disk where
    # concurrency only causes seeking.
    copy_threads: int = 8

    # How long the archive and status workers idle between polls. These loops
    # are pure Python, so spinning without a pause holds the GIL against the
    # storage threads doing the copying and throttles every archive in flight.
    # Lower it for snappier pickup of new manifests, raise it to leave more
    # room for large transfers.
    worker_poll_interval_seconds: float = 1.0

    # Reserved librarian name used by the CLI archive path. Jobs submitted
    # under this name never trigger a Librarian callback.
    cli_librarian_name: str = "__cli__"

    # Per-Librarian callback destinations, keyed by librarian_name. A completed
    # archive whose librarian_name is a key here is reported back. A name that
    # is neither the CLI name nor a key here is treated as a misconfiguration
    # (attempted, warned, and retried like a delivery failure).
    librarians: dict[str, LibrarianCallbackConfig] = {}
    clients: dict[str, ClientConfig] = {}

    # Reject unauthenticated submissions.
    require_client_auth: bool = True

    # Callback retry policy (dedicated loop).
    callback_max_attempts: int = 5
    callback_retry_base_seconds: float = 30.0  # exponential backoff base
    callback_poll_interval_seconds: float = 5.0
    callback_timeout_seconds: float = 30.0

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

        for name, cfg in __context.librarians.items():
            if cfg.password_file is not None:
                with open(cfg.password_file, "r") as handle:
                    cfg.password = handle.read().strip()
            if name == __context.cli_librarian_name:
                raise ValueError(f"Configured librarian '{name}' collides with cli_librarian_name.")

        for cfg in __context.clients.values():
            if cfg.password_file is not None:
                with open(cfg.password_file, "r") as handle:
                    cfg.password = handle.read().strip()

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

    # Return the cached object rather than re-reading the config file. The
    # background workers call this on every loop iteration, and rebuilding a
    # BaseSettings means a disk read plus a full pydantic-settings
    # construction -- pure Python, holding the GIL, starving the storage
    # threads doing the actual copying. Tests reset `_settings` to None to
    # force a reload.
    if _settings is not None:
        return _settings

    try_paths = [
        os.environ.get("ARCHIVIST_CONFIG_PATH", None),
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
                raise

            return _settings
    try:
        _settings = Settings()
    except ValidationError as e:
        print(f"Not all settings have defaults: {e}")
        raise

    return _settings


def __getattr__(name) -> Settings:
    """
    Try to load the settings if they haven't been loaded yet.
    """

    if name == "server_settings":
        if _settings is not None:
            return _settings

        return get_settings()

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
