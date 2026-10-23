"""Avoid starvation of persistent Telegram windows by slow optional sources."""
import asyncio
from types import SimpleNamespace

import pytest

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


@pytest.mark.asyncio
async def test_dedicated_window_worker_starts_before_slow_direct_feed_finishes():
    app = OptimizedHardenedOrchestrator.__new__(OptimizedHardenedOrchestrator)
    app._windows_need_reserved_worker = True
    app._single_worker_parallel_windows = False
    app._window_worker_claimed = False
    event = asyncio.Event()
    release = asyncio.Event()
    events = []

    async def direct(source, results, lock, timeout):
        events.append("direct-start")
        await release.wait()
        events.append("direct-finished")

    async def windows(results, lock, timeout):
        event.set()
        events.append("windows")

    app._source_timeout = lambda: 20.0
    app._run_direct_source = direct
    app._run_persistent_windows = windows
    source_queue = asyncio.Queue()
    source_queue.put_nowait(SimpleNamespace(type="http_subscription"))
    results = {"ok": 0, "err": 0}
    lock = asyncio.Lock()
    task1 = asyncio.create_task(app._worker_async(source_queue, results, lock))
    task2 = asyncio.create_task(app._worker_async(source_queue, results, lock))
    await asyncio.wait_for(event.wait(), timeout=1)
    assert "direct-finished" not in events
    release.set()
    await asyncio.gather(task1, task2)
    assert source_queue.empty()
    assert "windows" in events


@pytest.mark.asyncio
async def test_single_worker_allows_window_history_and_direct_feed_progress():
    app = OptimizedHardenedOrchestrator.__new__(OptimizedHardenedOrchestrator)
    app._windows_need_reserved_worker = False
    app._single_worker_parallel_windows = True
    app._window_worker_claimed = False
    started = asyncio.Event()
    events = []

    async def direct(source, results, lock, timeout):
        events.append("direct")
        started.set()
        await asyncio.sleep(0)

    async def windows(results, lock, timeout):
        await started.wait()
        events.append("windows")

    app._source_timeout = lambda: 20.0
    app._run_direct_source = direct
    app._run_persistent_windows = windows
    queue = asyncio.Queue()
    queue.put_nowait(SimpleNamespace(type="http_subscription"))
    await asyncio.wait_for(
        app._worker_async(queue, {"ok": 0, "err": 0}, asyncio.Lock()), timeout=1,
    )
    assert events == ["direct", "windows"]
