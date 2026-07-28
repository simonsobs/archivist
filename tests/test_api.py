# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""
Tests for the FastAPI routes in archivist.api.

These build a bare FastAPI app that includes the same routers as the real
server (`archivist.server.main`), but skip the lifespan handler -- which
starts busy-looping background worker threads -- since it isn't relevant
to exercising the HTTP endpoints themselves.
"""

import pytest
from conftest import make_manifest_request
from fastapi import FastAPI
from fastapi.testclient import TestClient

from archivist.api import health_router
from archivist.api import router as api_router
from archivist.database import yield_session
from archivist.orm.archive import Archive
from archivist.settings import get_settings


@pytest.fixture
def client(db_session, use_settings):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(health_router)

    def _yield_session():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: use_settings
    app.dependency_overrides[yield_session] = _yield_session

    return TestClient(app)


def test_health(client, use_settings):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "name": use_settings.displayed_site_name}


def test_archive_queues_the_manifest_and_returns_its_id(client, db_session):
    """The route enqueues rather than archiving synchronously; the queued row is the contract."""

    response = client.post("/api/v1/archive", json=make_manifest_request(json_safe=True))

    assert response.status_code == 200
    manifest_id = response.json()["manifest_id"]

    item = db_session.query(Archive).filter_by(manifest_id=manifest_id).one()
    assert not item.consumed
    assert not item.completed


def test_archive_rejects_manifests_over_the_size_limit(client, use_settings):
    use_settings.maximal_size_bytes = 100

    response = client.post("/api/v1/archive", json=make_manifest_request(json_safe=True, size=1_000_000))

    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.parametrize("endpoint", ["/api/v1/archive", "/api/v1/extract"])
def test_endpoints_reject_a_manifest_without_a_librarian_name(client, endpoint):
    payload = make_manifest_request(json_safe=True)
    del payload["librarian_name"]

    assert client.post(endpoint, json=payload).status_code == 422
