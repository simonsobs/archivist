Deployment
==========

We recommend deploying the archivist with containers, on the same compose network
as the librarian it serves. You will need three containers:

1. A PostgreSQL database for the archivist (separate from the librarian's).
2. A one-shot migration container that creates or upgrades the database schema.
3. The archivist server.

The archivist does not create its schema on startup. Run the migrations when
the database is first created, and again after any upgrade that adds them;
ordinary restarts do not need them.

Mounts
------

The archivist container needs three mounts:

- The configuration directory at ``/etc/archivist``, containing ``config.json``.
- The librarian's store, **at the same path** the librarian uses. The archivist
  reads each file at the ``instance_path`` given in the manifest. Mount it
  read-only.
- The archive storage, at the ``archive_root`` in the configuration.

The archivist creates any directories it needs below ``archive_root``.

Compose Example
---------------

.. code-block:: yaml

    services:
      archivist-database:
        image: postgres:16
        restart: always
        volumes:
          - /data/archivist_data:/var/lib/postgresql/data
        environment:
          POSTGRES_USER: "archivist"
          POSTGRES_DB: "archivist"
          POSTGRES_PASSWORD_FILE: /run/secrets/archivist_db_password
        secrets: [archivist_db_password]
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U archivist -d archivist"]
          interval: 10s
          retries: 5

      archivist-migrate:
        image: simonsobs/archivist:v0.1.0
        restart: "no"
        entrypoint: ["alembic", "-c", "/archivist/alembic.ini", "upgrade", "head"]
        volumes:
          - /data/archivist/config:/etc/archivist
        secrets: [archivist_db_password, archivist_authenticator]
        depends_on:
          archivist-database:
            condition: service_healthy

      archivist:
        image: simonsobs/archivist:v0.1.0
        restart: always
        volumes:
          - /data/archivist/config:/etc/archivist
          - /gpfs/SIMONSOBS/so/tracked:/gpfs/SIMONSOBS/so/tracked:ro
          - /tigerdata/so/archive:/tigerdata/so/archive
        secrets: [archivist_db_password, archivist_authenticator]
        depends_on:
          archivist-migrate:
            condition: service_completed_successfully

    secrets:
      archivist_db_password:
        file: /data/archivist/secrets/db_password
      archivist_authenticator:
        file: /data/archivist/secrets/authenticator_password

The migration container needs the secrets too, because loading the configuration
reads every password file.

Migrations
----------

To run the migrations by hand:

.. code-block:: bash

    podman compose run --rm archivist-migrate

A database created before the archivist used migrations already has its tables but
no migration record. Mark it as up to date once, before the first upgrade:

.. code-block:: bash

    podman compose run --rm --entrypoint alembic archivist-migrate \
        -c /archivist/alembic.ini stamp head
