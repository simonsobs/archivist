# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.core.librarian_client.send_archive_callback."""

import unittest
import unittest.mock

import requests

import archivist.core.librarian_client as client_module
from archivist.core.librarian_client import send_archive_callback
from archivist.settings import LibrarianCallbackConfig


def _ok_response():
    response = unittest.mock.Mock(status_code=200)
    response.raise_for_status.return_value = None
    return response


class TestSendArchiveCallback(unittest.TestCase):
    def test_posts_to_the_callback_path(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1")

        args, _ = mock_post.call_args
        self.assertEqual(args[0], "https://librarian.example.org/api/v2/archive/callback")

    def test_trailing_slash_on_base_url_does_not_double_up(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org/")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1")

        args, _ = mock_post.call_args
        self.assertEqual(args[0], "https://librarian.example.org/api/v2/archive/callback")

    def test_body_reports_manifest_and_success_status(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="manifest-42")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"manifest_id": "manifest-42", "status": "success"})

    def test_auth_token_becomes_a_bearer_header(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org", auth_token="s3cret")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer s3cret")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

    def test_no_auth_header_when_token_absent(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1")

        _, kwargs = mock_post.call_args
        self.assertNotIn("Authorization", kwargs["headers"])

    def test_timeout_is_forwarded(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1", timeout=7.5)

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], 7.5)

    def test_default_timeout_is_thirty_seconds(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=_ok_response()) as mock_post:
            send_archive_callback(config, manifest_id="m1")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], 30.0)

    def test_non_2xx_raises(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")
        response = unittest.mock.Mock(status_code=500)
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        with unittest.mock.patch.object(client_module.requests, "post", return_value=response):
            with self.assertRaises(requests.exceptions.HTTPError):
                send_archive_callback(config, manifest_id="m1")

    def test_transport_error_propagates(self):
        config = LibrarianCallbackConfig(url="https://librarian.example.org")

        with unittest.mock.patch.object(
            client_module.requests, "post", side_effect=requests.exceptions.ConnectionError("no route")
        ):
            with self.assertRaises(requests.exceptions.ConnectionError):
                send_archive_callback(config, manifest_id="m1")


if __name__ == "__main__":
    unittest.main()
