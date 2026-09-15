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
        ("_callback_worker_loop", "archivist.tasks.callback.process_callbacks"),
    ],
)
def test_worker_loops_survive_a_failed_iteration_and_stop_on_the_event(loop_name, patch_target, use_settings):
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
        mock.patch.object(server_module, "_callback_worker_loop", lambda: started.append("callback")),
        mock.patch.object(server_module, "find_orphaned_archives", return_value=[7, 9]) as mock_find,
        mock.patch.object(server_module, "reconcile_orphaned_archives") as mock_reconcile,
    ):
        asyncio.run(_run())

    # The snapshot is taken inline, before any worker starts: that ordering is
    # what stops a newly-dequeued manifest being mistaken for an orphan.
    mock_find.assert_called_once()
    # Reconciliation runs on a worker thread, but the lifespan's shutdown waits
    # for the pool, so by here it has run -- with the ids captured up front.
    mock_reconcile.assert_called_once_with([7, 9])
    assert sorted(started) == ["archive", "callback", "status"]
    assert server_module._archive_stop_event.is_set()
