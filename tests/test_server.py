# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.server (FastAPI app factory, lifespan, worker loops)."""

import asyncio
import threading
import unittest
import unittest.mock

import pytest

import archivist.server as server_module
from archivist.settings import Settings


@pytest.fixture(autouse=True)
def _reset_stop_event():
    """`_archive_stop_event` is module-level shared state; keep it clean per test."""

    server_module._archive_stop_event.clear()
    yield
    server_module._archive_stop_event.clear()


class TestMain(unittest.TestCase):
    def test_main_builds_app_with_settings_metadata(self):
        settings = Settings(
            displayed_site_name="My Archivist",
            displayed_site_description="A description",
            debug=False,
        )
        with unittest.mock.patch.object(server_module, "server_settings", settings):
            app = server_module.main()

        self.assertEqual(app.title, "My Archivist")
        self.assertEqual(app.description, "A description")
        self.assertIsNone(app.openapi_url)

    def test_main_enables_openapi_when_debug(self):
        settings = Settings(debug=True)
        with unittest.mock.patch.object(server_module, "server_settings", settings):
            app = server_module.main()

        self.assertEqual(app.openapi_url, "/api/v2/openapi.json")

    def test_main_registers_health_and_archive_routes(self):
        settings = Settings()
        with unittest.mock.patch.object(server_module, "server_settings", settings):
            app = server_module.main()

        paths = set(app.openapi()["paths"].keys())
        self.assertIn("/health", paths)
        self.assertIn("/api/v1/archive", paths)

    def test_main_wires_up_the_shared_lifespan_handler(self):
        """
        `main()` doesn't set `app.router.lifespan_context` to
        `slack_post_at_startup_shutdown` directly -- FastAPI wraps it in an
        internal `merged_lifespan` closure. Drive it through a real
        (mocked-out) startup/shutdown cycle instead of asserting identity.
        """
        settings = Settings()

        async def _run():
            with unittest.mock.patch.object(server_module, "server_settings", settings):
                app = server_module.main()

            with (
                unittest.mock.patch.object(server_module, "_archive_worker_loop", lambda: None),
                unittest.mock.patch.object(server_module, "_status_worker_loop", lambda: None),
                unittest.mock.patch.object(server_module, "reconcile_orphaned_archives"),
                unittest.mock.patch("archivist.database.create_all") as mock_create_all,
            ):
                async with app.router.lifespan_context(app):
                    pass

            mock_create_all.assert_called_once()

        asyncio.run(_run())


class TestArchiveWorkerLoop(unittest.TestCase):
    def test_calls_start_archive_until_stopped(self):
        settings = Settings(name="test-server")
        call_count = 0

        def _fake_start_archive(librarian_name):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                server_module._archive_stop_event.set()

        with (
            unittest.mock.patch.object(server_module, "server_settings", settings),
            unittest.mock.patch("archivist.tasks.archive.start_archive", side_effect=_fake_start_archive),
        ):
            thread = threading.Thread(target=server_module._archive_worker_loop)
            thread.start()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(call_count, 3)

    def test_survives_exceptions_and_keeps_looping(self):
        call_count = 0

        def _fake_start_archive(librarian_name):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            server_module._archive_stop_event.set()

        with unittest.mock.patch("archivist.tasks.archive.start_archive", side_effect=_fake_start_archive):
            thread = threading.Thread(target=server_module._archive_worker_loop)
            thread.start()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(call_count, 2)

    def test_noop_when_stop_event_already_set(self):
        server_module._archive_stop_event.set()

        with unittest.mock.patch("archivist.tasks.archive.start_archive") as mock_start:
            server_module._archive_worker_loop()

        mock_start.assert_not_called()


class TestStatusWorkerLoop(unittest.TestCase):
    def test_calls_process_status_queue_until_stopped(self):
        call_count = 0

        def _fake_process():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                server_module._archive_stop_event.set()

        with unittest.mock.patch("archivist.tasks.archive.process_status_queue", side_effect=_fake_process):
            thread = threading.Thread(target=server_module._status_worker_loop)
            thread.start()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(call_count, 3)

    def test_survives_exceptions_and_keeps_looping(self):
        call_count = 0

        def _fake_process():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            server_module._archive_stop_event.set()

        with unittest.mock.patch("archivist.tasks.archive.process_status_queue", side_effect=_fake_process):
            thread = threading.Thread(target=server_module._status_worker_loop)
            thread.start()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(call_count, 2)


class TestLifespan(unittest.TestCase):
    def test_lifespan_creates_schema_starts_workers_and_stops_on_exit(self):
        submitted = []

        def _fake_archive_loop():
            submitted.append("archive")

        def _fake_status_loop():
            submitted.append("status")

        async def _run():
            app = unittest.mock.Mock()
            async with server_module.slack_post_at_startup_shutdown(app):
                # Give the submitted worker threads a beat to run.
                await asyncio.sleep(0.1)

        with (
            unittest.mock.patch.object(server_module, "_archive_worker_loop", _fake_archive_loop),
            unittest.mock.patch.object(server_module, "_status_worker_loop", _fake_status_loop),
            unittest.mock.patch.object(server_module, "reconcile_orphaned_archives") as mock_reconcile,
            unittest.mock.patch("archivist.database.create_all") as mock_create_all,
        ):
            asyncio.run(_run())

        mock_create_all.assert_called_once()
        mock_reconcile.assert_called_once()
        self.assertIn("archive", submitted)
        self.assertIn("status", submitted)
        self.assertTrue(server_module._archive_stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
