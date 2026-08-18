"""
Authentication for inbound manifest submissions.

A client proves who it is by presenting the shared secret configured for it
under `settings.clients[<name>].auth_token`, usually via `auth_token_file` --
the same file is read by the Librarian that submits manifests, and by
Archivist's own CLI archive path.

Because tokens are per-client, verifying one also establishes *which* client
is calling; the route binds that identity to the `librarian_name` in the body,
so a valid token for one Librarian cannot be used to submit work under
another's name.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from archivist.settings import Settings, get_settings

security = HTTPBearer(auto_error=False)

UnauthorizedError = HTTPException(
    status_code=401,
    detail="Missing or invalid authentication token",
    headers={"WWW-Authenticate": "Bearer"},
)


def resolve_submitter(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str | None:
    """Return the librarian name owning the presented token, or None if auth is off."""

    if not settings.require_client_auth:
        return None

    presented = credentials.credentials if credentials is not None else ""
    if not presented:
        logger.warning("Rejected a manifest submission carrying no bearer token.")
        raise UnauthorizedError

    # compare_digest rejects non-ASCII str outright, and the presented value
    # comes straight off the wire, so compare bytes instead -- otherwise a junk
    # Authorization header is a 500 rather than a 401.
    presented_bytes = presented.encode("utf-8")

    # Every configured token is compared rather than stopping at the first
    # match, so the work done does not vary with which client is calling;
    # compare_digest keeps it from varying with how much of a token is right.
    matched = None
    for name, cfg in settings.clients.items():
        if cfg.enabled and cfg.auth_token and secrets.compare_digest(presented_bytes, cfg.auth_token.encode("utf-8")):
            matched = name

    if matched is None:
        logger.warning("Rejected a manifest submission with an unrecognised bearer token.")
        raise UnauthorizedError

    return matched


SubmitterDependency = Annotated[str | None, Depends(resolve_submitter)]
