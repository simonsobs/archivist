# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.database engine/session helpers."""

import unittest
import unittest.mock

import pytest
from sqlalchemy.orm import Session

import archivist.database as database


@pytest.mark.usefixtures("use_settings")
class TestDatabaseBase(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _inject(self, use_settings):
        self.settings = use_settings


class TestGetEngine(TestDatabaseBase):
    def test_engine_is_created_lazily_and_cached(self):
        self.assertIsNone(database._engine)

        engine = database.get_engine()

        self.assertIsNotNone(database._engine)
        self.assertIs(engine, database.get_engine())


class TestGetSessionmaker(TestDatabaseBase):
    def test_sessionmaker_is_created_lazily_and_cached(self):
        self.assertIsNone(database._SessionMaker)

        maker = database.get_sessionmaker()

        self.assertIsNotNone(database._SessionMaker)
        self.assertIs(maker, database.get_sessionmaker())


class TestGetSession(TestDatabaseBase):
    def test_returns_a_session_the_caller_must_close(self):
        database.create_all()
        session = database.get_session()
        try:
            self.assertIsInstance(session, Session)
        finally:
            session.close()


class TestYieldSession(TestDatabaseBase):
    def test_yields_a_session_and_closes_it_afterwards(self):
        database.create_all()
        generator = database.yield_session()

        session = next(generator)
        self.assertIsInstance(session, Session)

        # Draining the generator triggers the `finally: session.close()`.
        with self.assertRaises(StopIteration):
            next(generator)

    def test_closes_session_even_if_consumer_raises(self):
        database.create_all()
        generator = database.yield_session()
        session = next(generator)

        with unittest.mock.patch.object(session, "close") as mock_close:
            with self.assertRaises(RuntimeError):
                generator.throw(RuntimeError("boom"))

        mock_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
