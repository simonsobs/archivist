"""
HTTP mechanism for reporting a completed archive back to a Librarian.

One stateless attempt per call: this module knows how to build and send the
request, and raises on transport error or non-2xx. All delivery-guarantee
logic (retries, backoff, giving up) lives in
`archivist.tasks.callback.process_callbacks`.
"""

import requests

from archivist.settings import LibrarianCallbackConfig

CALLBACK_PATH = "api/v2/archive/callback"


def send_archive_callback(
    config: LibrarianCallbackConfig,
    manifest_id: str,
    archive_name: str,
    archive_id: str,
    archive_path: str,
    timeout: float = 30.0,
) -> None:
    """
    POST an archive completion report to a Librarian.

    The body matches the Librarian's `ArchiveCallbackRequest`; every field is
    required there, so an incomplete report is a 422 rather than a partial
    update.

    Parameters
    ----------
    config : LibrarianCallbackConfig
        The destination Librarian's base URL and (optional) auth token.
    manifest_id : str
        The manifest that has been archived.
    archive_name : str
        The archive name the Librarian sent with the manifest.
    archive_id : str
        Archivist's ID for the archive (the same value as `manifest_id`).
    archive_path : str
        Where the archived data landed.
    timeout : float
        Per-request timeout, in seconds.

    Raises
    ------
    requests.RequestException
        On a transport error or a non-2xx response.
    """
    url = f"{config.url.rstrip('/')}/{CALLBACK_PATH}"
    headers = {"Content-Type": "application/json"}
    if config.auth_token:
        headers["Authorization"] = f"Bearer {config.auth_token}"
    resp = requests.post(
        url,
        json={
            "manifest_id": manifest_id,
            "archive_name": archive_name,
            "archive_id": archive_id,
            "archive_path": archive_path,
        },
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
