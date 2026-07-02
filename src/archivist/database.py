"""
Core database runner for SQLAlchemy.
"""

from loguru import logger
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    PickleType,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import server_settings

logger.info("Starting database engine.")

# Create the engine and sessionmaker.
engine = create_engine(
    server_settings.sqlalchemy_database_uri,
    # Required for async and SQLite
    connect_args=({"check_same_thread": False} if "sqlite" in server_settings.sqlalchemy_database_uri else {}),
)

logger.info("Creating database session.")

SessionMaker = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def yield_session() -> SessionMaker:
    """
    Yields a new databse session.
    """

    session = SessionMaker()
    try:
        yield session
    finally:
        session.close()


def get_session() -> SessionMaker:
    """
    Returns a new database session. Unlike yield_session, it is
    your responsibility to close the session.
    """

    return SessionMaker()


Base = declarative_base()


def create_all() -> None:
    """
    Create all tables that don't already exist. Imports the ORM models
    first so their table definitions are registered with `Base`.
    """

    from . import orm  # noqa: F401

    Base.metadata.create_all(engine)
