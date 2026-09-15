Configuration
=============

The archivist is configured with a single JSON file, passed with ``-c``
(``archivist -c config.json start-server``) or through the ``ARCHIVIST_CONFIG_PATH``
environment variable. In the container image the file is expected at
``/etc/archivist/config.json``. Settings are read at startup, so restart the
archivist after changing them.

The configuration variables are as follows:

- ``name``: The name of this archivist. It is sent with every callback, and must
  match the ``--name`` the archivist is registered under on the librarian.
- ``debug``: Enables the API docs. Set to ``false`` in production.
- ``log_level``: The log level. We recommend ``INFO`` for production.
- ``host``: The host to bind to. Set to ``0.0.0.0`` inside a container.
- ``port``: The port to bind to (default ``8080``).
- ``displayed_site_name``, ``displayed_site_description``: Shown by the health
  endpoint.
- Database settings:

  * ``database_driver``: The SQLAlchemy driver, e.g. ``postgresql``.
  * ``database_host``, ``database_port``, ``database``: Where the database is.
  * ``database_user``: The database user.
  * ``database_password_file``: File containing the database password. Use
    ``database_password`` only for local testing.
- Storage settings:

  * ``archive_type``: The storage backend. Only ``posix`` is implemented.
  * ``local_root``: The common root of the librarian's files. Must be a parent of
    every ``instance_path`` the librarian sends.
  * ``archive_root``: Where archived files are written. A file at
    ``local_root/a/b.txt`` is archived to ``archive_root/a/b.txt``.
  * ``maximal_size_bytes``: The largest manifest accepted, in bytes. Must be at
    least the librarian's ``filesize_per_run``.
- Throughput settings:

  * ``storage_threads``: Archive jobs copied at the same time. We recommend ``1``.
  * ``copy_threads``: Files copied at the same time within one job. Use ``8`` for
    network storage and ``1`` for local disk. Total concurrent copies are
    ``storage_threads × copy_threads``.
  * ``copy_attempts``: Attempts per file before the copy counts as failed.
  * ``copy_retry_base_seconds``: Delay before the first retry, doubling after each.
  * ``worker_poll_interval_seconds``: How often idle workers check for new work.
  * ``max_archive_retries``: Times an interrupted job is retried on restart before
    it is marked failed.
- Librarian settings (see :doc:`Librarians`):

  * ``clients``: Librarians allowed to submit manifests, and their credentials.
  * ``librarians``: Where to send callbacks, and the credentials to use.
  * ``require_client_auth``: Reject manifests without valid credentials (default
    ``true``).
  * ``cli_librarian_name``: The name used for jobs submitted with the command
    line. These never send a callback.
- Callback settings:

  * ``callback_max_attempts``: Attempts before a callback is marked failed.
  * ``callback_retry_base_seconds``: Delay before the first retry, doubling after each.
  * ``callback_poll_interval_seconds``: How often the callback worker checks for work.
  * ``callback_timeout_seconds``: Timeout for each callback request.

Store every password in a file and point to it with a ``password_file`` setting.

An example configuration:

.. code-block:: json

    {
      "name": "archivist-princeton",
      "host": "0.0.0.0",
      "port": 8080,
      "log_level": "INFO",

      "database_driver": "postgresql",
      "database_host": "archivist-database",
      "database_port": 5432,
      "database": "archivist",
      "database_user": "archivist",
      "database_password_file": "/run/secrets/archivist_db_password",

      "archive_type": "posix",
      "local_root": "/gpfs/SIMONSOBS/so/tracked",
      "archive_root": "/tigerdata/so/archive",
      "maximal_size_bytes": 549755813888,

      "storage_threads": 1,
      "copy_threads": 8,
      "worker_poll_interval_seconds": 30.0,
      "max_archive_retries": 20,

      "librarians": {
        "princeton_librarian": {
          "url": "http://librarian:21109",
          "username": "archuser",
          "password_file": "/run/secrets/archivist_authenticator"
        }
      },
      "clients": {
        "princeton_librarian": {
          "username": "archuser",
          "password_file": "/run/secrets/archivist_authenticator"
        }
      }
    }
