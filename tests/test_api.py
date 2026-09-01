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
from conftest import LIBRARIAN_CREDENTIALS, make_manifest_request
from fastapi import FastAPI
from fastapi.testclient import TestClient

from archivist.api import health_router
from archivist.api import router as api_router
from archivist.database import yield_session
from archivist.orm.archive import Archive
from archivist.orm.manifest import Manifest
from archivist.settings import get_settings


def _client(db_session, use_settings, credentials=None):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(health_router)

    def _yield_session():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: use_settings
    app.dependency_overrides[yield_session] = _yield_session

    return TestClient(app, auth=credentials)


@pytest.fixture
def client(db_session, use_settings):
    """Authenticated as `test-librarian`, the name manifests are submitted under."""

    return _client(db_session, use_settings, LIBRARIAN_CREDENTIALS)


@pytest.fixture
def anon_client(db_session, use_settings):
    return _client(db_session, use_settings)


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
    # Archivist mints its own archive id; the Librarian stores it in its own
    # column and no longer requires it to equal the manifest id.
    assert response.json()["archive_id"] == item.id != manifest_id


@pytest.mark.parametrize(
    "credentials",
    [None, ("archuser", "wrong-password"), ("nobody", LIBRARIAN_CREDENTIALS[1])],
    ids=["no-credentials", "wrong-password", "unknown-username"],
)
def test_archive_rejects_an_unauthenticated_submission(anon_client, db_session, credentials):
    response = anon_client.post(
        "/api/v1/archive", json=make_manifest_request(json_safe=True), auth=credentials
    )

    assert response.status_code == 401
    assert db_session.query(Archive).count() == 0


def test_archive_rejects_a_manifest_naming_another_librarian(client, db_session):
    """A valid token is not a licence to submit under someone else's name."""

    payload = make_manifest_request(json_safe=True)
    payload["librarian_name"] = "other-librarian"

    assert client.post("/api/v1/archive", json=payload).status_code == 403
    assert db_session.query(Archive).count() == 0


def test_disabling_auth_accepts_an_unauthenticated_submission(anon_client, use_settings):
    """The rollout switch: it has to actually open, or staging the change is impossible."""

    use_settings.require_client_auth = False

    assert anon_client.post("/api/v1/archive", json=make_manifest_request(json_safe=True)).status_code == 200


def test_a_disabled_clients_credentials_stop_working(anon_client, use_settings, db_session):
    """Revocation path: `enabled: false` without dropping the entry and its password file."""

    use_settings.clients["test-librarian"].enabled = False

    response = anon_client.post(
        "/api/v1/archive",
        json=make_manifest_request(json_safe=True),
        auth=LIBRARIAN_CREDENTIALS,
    )

    assert response.status_code == 401
    assert db_session.query(Archive).count() == 0


def test_auth_is_checked_before_the_size_limit(anon_client, use_settings):
    """An unauthorised caller shouldn't be able to probe limits."""

    use_settings.maximal_size_bytes = 100

    response = anon_client.post("/api/v1/archive", json=make_manifest_request(json_safe=True, size=1_000_000))

    assert response.status_code == 401


def test_health_needs_no_token(anon_client):
    assert anon_client.get("/health").status_code == 200


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


@pytest.mark.parametrize(
    "resubmitted_name,resubmitted_checksum,expected_status",
    [
        ("a.txt", "a" * 64, 200),
        ("a.txt", "b" * 64, 409),
    ],
    ids=["same-content-is-a-noop", "different-content-conflicts"],
)
def test_resubmitting_a_manifest_id(client, db_session, resubmitted_name, resubmitted_checksum, expected_status):
    """
    A manifest is immutable and identified by the Librarian-minted
    `manifest_id`, which therefore doubles as an idempotency key. Archivist
    queues asynchronously and returns immediately, so a lost response makes
    the Librarian retry: an identical resend must be a noop, and a changed
    one must be rejected rather than silently mutating the manifest.
    """

    first = make_manifest_request(id="m-dup", json_safe=True, name="a.txt", checksum="a" * 64)
    second = make_manifest_request(id="m-dup", json_safe=True, name=resubmitted_name, checksum=resubmitted_checksum)

    assert client.post("/api/v1/archive", json=first).status_code == 200
    assert client.post("/api/v1/archive", json=second).status_code == expected_status

    # Either way, exactly one archive job and the original entry survive.
    assert db_session.query(Archive).filter_by(manifest_id="m-dup").count() == 1

    db_session.expire_all()
    manifest = db_session.get(Manifest, "m-dup")
    assert len(manifest.entries) == 1
    assert manifest.entries[0].checksum == "a" * 64


def test_distinct_manifest_ids_create_distinct_jobs(client, db_session):
    """Same content under different ids is not a duplicate; the id is the key, not the payload."""

    for manifest_id in ("m-one", "m-two"):
        payload = make_manifest_request(id=manifest_id, json_safe=True)
        assert client.post("/api/v1/archive", json=payload).status_code == 200

    assert db_session.query(Archive).count() == 2
