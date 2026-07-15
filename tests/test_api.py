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
from archivist.orm.archive import Archive
from archivist.orm.manifest import Manifest
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
            "manifest_id": "m-valid",
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json()],
        }

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("manifest_id", body)

    def test_archive_persists_queue_item(self):
        payload = {
            "manifest_id": "m-persist",
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json()],
        }

        response = self.client.post("/api/v1/archive", json=payload)
        manifest_id = response.json()["manifest_id"]

        item = self.session.query(Archive).filter_by(manifest_id=manifest_id).one()
        self.assertFalse(item.consumed)
        self.assertFalse(item.completed)

    def test_archive_over_size_limit_returns_400(self):
        self.settings.maximal_size_bytes = 100

        payload = {
            "manifest_id": "m-oversize",
            "librarian_name": "test-librarian",
            "store_files": [make_manifest_entry_json(size=1_000_000)],
        }

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_archive_empty_store_files_succeeds(self):
        payload = {"manifest_id": "m-empty", "librarian_name": "test-librarian", "store_files": []}

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 200)

    def test_archive_missing_librarian_name_returns_422(self):
        payload = {"store_files": [make_manifest_entry_json()]}

        response = self.client.post("/api/v1/archive", json=payload)

        self.assertEqual(response.status_code, 422)


class TestArchiveIdempotency(TestApiBase):
    """
    A manifest is immutable and identified by the Librarian-minted
    `manifest_id`, which therefore doubles as an idempotency key. Resubmitting
    the same id must be safe: identical content is a noop, differing content is
    a conflict. See `archivist.api.archive.archive`.
    """

    def _post(self, manifest_id, store_files, **extra):
        payload = {
            "manifest_id": manifest_id,
            "librarian_name": "test-librarian",
            "store_files": store_files,
            **extra,
        }
        return self.client.post("/api/v1/archive", json=payload)

    def test_resubmit_same_content_is_noop(self):
        files = [make_manifest_entry_json(name="a.txt", checksum="a" * 64)]

        first = self._post("m-dup", files)
        second = self._post("m-dup", files)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # Same id echoed back both times.
        self.assertEqual(first.json()["manifest_id"], "m-dup")
        self.assertEqual(second.json()["manifest_id"], "m-dup")
        # The noop path must not enqueue a second archive job for the manifest.
        self.assertEqual(self.session.query(Archive).filter_by(manifest_id="m-dup").count(), 1)

    def test_resubmit_reordered_content_is_noop(self):
        a = make_manifest_entry_json(name="a.txt", checksum="a" * 64)
        b = make_manifest_entry_json(name="b.txt", checksum="b" * 64)

        first = self._post("m-order", [a, b])
        second = self._post("m-order", [b, a])

        # Content is compared as a sorted (name, checksum) set, so file order
        # in the request must not matter.
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.session.query(Archive).filter_by(manifest_id="m-order").count(), 1)

    def test_resubmit_different_content_returns_409(self):
        original = [make_manifest_entry_json(name="a.txt", checksum="a" * 64)]
        changed = [make_manifest_entry_json(name="a.txt", checksum="b" * 64)]

        first = self._post("m-conflict", original)
        second = self._post("m-conflict", changed)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertIn("error", second.json())

    def test_conflict_leaves_original_manifest_unchanged(self):
        original = [make_manifest_entry_json(name="a.txt", checksum="a" * 64)]
        changed = [make_manifest_entry_json(name="a.txt", checksum="b" * 64)]

        self._post("m-immutable", original)
        self._post("m-immutable", changed)

        self.session.expire_all()
        manifest = self.session.get(Manifest, "m-immutable")
        # Immutability: the rejected resubmit must not mutate stored entries...
        self.assertEqual(len(manifest.entries), 1)
        self.assertEqual(manifest.entries[0].checksum, "a" * 64)
        # ...nor enqueue a second archive job.
        self.assertEqual(self.session.query(Archive).filter_by(manifest_id="m-immutable").count(), 1)

    def test_distinct_ids_create_distinct_manifests(self):
        files = [make_manifest_entry_json(name="a.txt", checksum="a" * 64)]

        first = self._post("m-one", files)
        second = self._post("m-two", files)

        # Same content under different ids is not a duplicate; both proceed.
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.session.query(Archive).count(), 2)


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
            "manifest_id": "m-extract",
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
