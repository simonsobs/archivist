"""Alembic environment for Archivist.

Wires Alembic to Archivist's settings-driven database configuration. The
target metadata is `database.Base.metadata`; importing `archivist.orm`
registers the `Manifest` / `ManifestEntry` / `Archive` tables on it. Mirrors
the sibling Librarian's `alembic/env.py`.
"""

# A hack so that `archivist` is importable when alembic is run from the repo
# root: the `src/` layout means the package lives under src/.
import sys

sys.path.insert(0, "src")

from logging.config import fileConfig

from alembic import context
from archivist import orm  # noqa: F401  (registers ORM tables on Base.metadata)
from archivist.database import Base, get_engine
from archivist.settings import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares this metadata against the live database.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode -- all we need is a URL."""
    url = get_settings().sqlalchemy_database_uri
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode -- using the actual Archivist database
    connection built from settings.
    """
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
