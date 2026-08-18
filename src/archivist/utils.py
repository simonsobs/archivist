import hashlib
from pathlib import Path


def _checksum(path: Path) -> str:
    """Compute the sha256 checksum of a file."""

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)

    return hasher.hexdigest()
