# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""
Tests for the FastAPI routes in archivist.api.

These build a bare FastAPI app that includes the same routers as the real
server (`archivist.server.main`), but skip the lifespan handler -- which
starts busy-looping background worker threads -- since it isn't relevant
to exercising the HTTP endpoints themselves.
"""

import unittest

import pytest
from conftest import make_manifest_entry_json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from archivist.api import health_router
from archivist.api import router as api_router
from archivist.database import yield_session
from archivist.orm.archivequeue import ArchiveQueue
from archivist.settings import get_settings


def _build_app(settings, session_factory):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(health_router)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[yield_session] = session_factory

    return app


@pytest.mark.usefixtures("db_session")
class TestApiBase(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _inject(self, db_session, use_settings):
        self.session = db_session
        self.settings = use_settings

        def _session_factory():
            yield self.session

        self.app = _build_app(self.settings, _session_factory)
        self.client = TestClient(self.app)


class TestHealthEndpoint(TestApiBase):
    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["name"], self.settings.displayed_site_name)


class TestArchiveEndpoint(TestApiBase):
    def test_archive_valid_manifest_returns_manifest_id(self):
        payload = {
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json()],
        }

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("manifest_id", body)

    def test_archive_persists_queue_item(self):
        payload = {
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json()],
        }

        response = self.client.post("/api/v1/archive", json=payload)
        manifest_id = response.json()["manifest_id"]

        item = self.session.query(ArchiveQueue).filter_by(manifest_id=manifest_id).one()
        self.assertFalse(item.consumed)
        self.assertFalse(item.completed)

    def test_archive_over_size_limit_returns_400(self):
        self.settings.maximal_size_bytes = 100

        payload = {
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json(size=1_000_000)],
        }

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_archive_empty_store_files_succeeds(self):
        payload = {"librarian_name": "test-librarian", "store_files": []}

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 200)

    def test_archive_missing_librarian_name_returns_422(self):
        payload = {"store_files": [make_manifest_entry_json()]}

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 422)


class TestExtractEndpoint(TestApiBase):
    """
    `/api/v1/extract` is currently an unimplemented stub (`archivist.api.extract.extract`
    just does `pass`, i.e. returns `None`). Since the route declares
    `response_model=ManifestResponse | ManifestFailedResponse`, returning `None`
    fails FastAPI's response validation. These tests document that current,
    not-yet-implemented behavior rather than asserting a "correct" outcome.
    """

    def test_extract_stub_raises_response_validation_error(self):
        no_raise_client = TestClient(self.app, raise_server_exceptions=False)

        payload = {
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json()],
        }
        response = no_raise_client.post("/api/v1/extract", json=payload)

        self.assertEqual(response.status_code, 500)

    def test_extract_missing_librarian_name_returns_422(self):
        payload = {"store_files": [make_manifest_entry_json()]}

        response = self.client.post("/api/v1/extract", json=payload)

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
