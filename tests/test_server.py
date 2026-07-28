# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.
import asyncio
import threading
from unittest import mock

import pytest

import archivist.server as server_module
from archivist.settings import Settings


@pytest.fixture(autouse=True)
def _reset_stop_event():
    """`_archive_stop_event` is module-level shared state; keep it clean per test."""

    server_module._archive_stop_event.clear()
    yield
    server_module._archive_stop_event.clear()


def test_main_builds_an_app_serving_the_routers():
    """uvicorn loads this factory by name, so a broken one fails only at runtime."""

    with mock.patch.object(server_module, "server_settings", Settings(debug=True)):
        app = server_module.main()

    assert {"/health", "/api/v1/archive"} <= set(app.openapi()["paths"].keys())


@pytest.mark.parametrize(
    "loop_name,patch_target",
    [
        ("_archive_worker_loop", "archivist.tasks.archive.start_archive"),
        ("_status_worker_loop", "archivist.tasks.archive.process_status_queue"),
    ],
)
def test_worker_loops_survive_a_failed_iteration_and_stop_on_the_event(loop_name, patch_target):
    """These busy-loop forever; an escaping exception would silently kill the worker."""

    call_count = 0

    def _fake(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        if call_count >= 3:
            server_module._archive_stop_event.set()

    with mock.patch(patch_target, side_effect=_fake):
        thread = threading.Thread(target=getattr(server_module, loop_name))
        thread.start()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert call_count >= 3


def test_lifespan_recovers_orphans_starts_workers_and_stops_them_on_exit():
    started = []

    async def _run():
        async with server_module.startup_shutdown_server(mock.Mock()):
            # Give the submitted worker threads a beat to run.
            await asyncio.sleep(0.1)

    with (
        mock.patch.object(server_module, "_archive_worker_loop", lambda: started.append("archive")),
        mock.patch.object(server_module, "_status_worker_loop", lambda: started.append("status")),
        mock.patch.object(server_module, "reconcile_orphaned_archives") as mock_reconcile,
        mock.patch("archivist.database.create_all") as mock_create_all,
    ):
        asyncio.run(_run())

    # Crash recovery has to run once, after the schema exists but before any
    # worker can dequeue -- otherwise it races the rows it is meant to reclaim.
    mock_create_all.assert_called_once()
    mock_reconcile.assert_called_once()
    assert sorted(started) == ["archive", "status"]
    assert server_module._archive_stop_event.is_set()
