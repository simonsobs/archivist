# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.core.models pydantic models."""

import unittest

from conftest import make_manifest_entry
from pydantic import ValidationError

from archivist.core.models import (
    ManifestEntry,
    ManifestFailedResponse,
    ManifestRequest,
    ManifestResponse,
)


class TestManifestEntry(unittest.TestCase):
    def test_valid_entry_constructs(self):
        entry = ManifestEntry(**make_manifest_entry())
        self.assertEqual(entry.name, "file.txt")
        self.assertEqual(entry.size, 1024)
        self.assertTrue(entry.instance_available)

    def test_missing_required_field_raises(self):
        data = make_manifest_entry()
        del data["checksum"]
        with self.assertRaises(ValidationError):
            ManifestEntry(**data)

    def test_wrong_type_raises(self):
        data = make_manifest_entry(size="not-a-number")
        with self.assertRaises(ValidationError):
            ManifestEntry(**data)


class TestManifestRequest(unittest.TestCase):
    def test_valid_request_constructs(self):
        request = ManifestRequest(
            librarian_name="lib",
            store_files=[make_manifest_entry(), make_manifest_entry(name="other.txt")],
        )
        self.assertEqual(request.librarian_name, "lib")
        self.assertEqual(len(request.store_files), 2)

    def test_empty_store_files_is_allowed(self):
        request = ManifestRequest(librarian_name="lib", store_files=[])
        self.assertEqual(request.store_files, [])

    def test_missing_librarian_name_raises(self):
        with self.assertRaises(ValidationError):
            ManifestRequest(store_files=[])


class TestManifestResponses(unittest.TestCase):
    def test_manifest_response(self):
        response = ManifestResponse(manifest_id="abc-123")
        self.assertEqual(response.manifest_id, "abc-123")

    def test_manifest_failed_response(self):
        response = ManifestFailedResponse(error="boom")
        self.assertEqual(response.error, "boom")


if __name__ == "__main__":
    unittest.main()
