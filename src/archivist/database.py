"""
Core database runner for SQLAlchemy.
"""

from collections.abc import Generator

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
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from .settings import get_settings

# Engine and sessionmaker are created lazily, on first use, rather than at
# import time. Settings (in particular the database path / ARCHIVIST_CONFIG_PATH)
# may not be finalized yet when this module is first imported -- e.g. the CLI
# sets ARCHIVIST_CONFIG_PATH from `--config` inside a click callback, which runs
# after all top-level imports have already happened.
_engine = None
_SessionMaker = None


def get_engine():
    """
    Returns the (lazily created) SQLAlchemy engine, built from the current settings.
    """

    global _engine

    if _engine is None:
        settings = get_settings()
        logger.info("Starting database engine.")
        _engine = create_engine(
            settings.sqlalchemy_database_uri,
            # Required for async and SQLite
            connect_args=({"check_same_thread": False} if "sqlite" in settings.sqlalchemy_database_uri else {}),
        )

    return _engine


def get_sessionmaker() -> sessionmaker:
    """
    Returns the (lazily created) sessionmaker, bound to the lazily created engine.
    """

    global _SessionMaker

    if _SessionMaker is None:
        logger.info("Creating database session.")
        _SessionMaker = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)

    return _SessionMaker


def yield_session() -> "Generator[Session, None, None]":
    """
    Yields a new databse session.
    """

    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def get_session() -> "Session":
    """
    Returns a new database session. Unlike yield_session, it is
    your responsibility to close the session.
    """

    return get_sessionmaker()()


Base = declarative_base()


def create_all() -> None:
    """
    Create all tables that don't already exist. Imports the ORM models
    first so their table definitions are registered with `Base`.
    """

    from . import orm

    Base.metadata.create_all(get_engine())
