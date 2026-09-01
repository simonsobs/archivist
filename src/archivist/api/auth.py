"""
Authentication for inbound manifest submissions.

A client proves who it is by presenting the HTTP Basic credentials configured
for it under `settings.clients[<name>]` -- the username, and a password
usually read from `password_file`. The same pair is held by the Librarian
that submits manifests (as its `archivists.authenticator` row) and by
Archivist's own CLI archive path.

The Basic username is not the Librarian's name: it is the username half of
that authenticator. Because credentials are per-client, verifying a pair also
establishes *which* client is calling -- the key it is filed under -- and the
route binds that identity to the `librarian_name` in the body, so one
Librarian's credentials cannot be used to submit work under another's name.

Basic over plain HTTP is deliberate: Librarian and Archivist share a Docker
network at every site, so the traffic never reaches a physical interface.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

from archivist.settings import Settings, get_settings

security = HTTPBasic(auto_error=False)

UnauthorizedError = HTTPException(
    status_code=401,
    detail="Missing or invalid credentials",
    headers={"WWW-Authenticate": "Basic"},
)


def resolve_submitter(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str | None:
    """Return the librarian name owning the presented credentials, or None if auth is off."""

    if not settings.require_client_auth:
        return None

    if credentials is None or not credentials.username:
        logger.warning("Rejected a manifest submission carrying no credentials.")
        raise UnauthorizedError

    # compare_digest rejects non-ASCII str outright, and the presented values
    # come straight off the wire, so compare bytes instead -- otherwise a junk
    # Authorization header is a 500 rather than a 401.
    presented_username = credentials.username.encode("utf-8")
    presented_password = credentials.password.encode("utf-8")

    # Every configured credential is compared rather than stopping at the first
    # match, so the work done does not vary with which client is calling;
    # compare_digest keeps it from varying with how much of a credential is
    # right. Both halves are always compared for the same reason.
    matched = None
    for name, cfg in settings.clients.items():
        if not (cfg.enabled and cfg.username and cfg.password):
            continue
        username_ok = secrets.compare_digest(presented_username, cfg.username.encode("utf-8"))
        password_ok = secrets.compare_digest(presented_password, cfg.password.encode("utf-8"))
        if username_ok & password_ok:
            matched = name

    if matched is None:
        logger.warning("Rejected a manifest submission with unrecognised credentials.")
        raise UnauthorizedError

    return matched


SubmitterDependency = Annotated[str | None, Depends(resolve_submitter)]
