import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator
from huntx.pipeline.optimized_transform import OptimizedTransformPipeline


def test_adaptive_transform_batch_size_scales_with_workers(monkeypatch):
    monkeypatch.delenv("HUNTX_TRANSFORM_BATCH_SIZE", raising=False)
    pipeline = object.__new__(OptimizedTransformPipeline)
    pipeline.max_workers = 10
    assert pipeline._effective_batch_size() == 640


def test_transform_batch_size_can_be_bounded(monkeypatch):
    monkeypatch.setenv("HUNTX_TRANSFORM_BATCH_SIZE", "99999")
    pipeline = object.__new__(OptimizedTransformPipeline)
    pipeline.max_workers = 2
    assert pipeline._effective_batch_size() == 2000


@pytest.mark.asyncio
async def test_source_timeout_is_isolated(monkeypatch):
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._ingest_one_source_async = AsyncMock(side_effect=asyncio.TimeoutError)
    monkeypatch.setenv("HUNTX_SOURCE_TIMEOUT", "30")
    queue = asyncio.Queue()
    queue.put_nowait(SimpleNamespace(id="slow-source"))
    results = {"ok": 0, "err": 0}
    await orchestrator._worker_async(queue, results, asyncio.Lock())
    assert results == {"ok": 0, "err": 1}
    assert queue.empty()


@pytest.mark.asyncio
async def test_incremental_sources_are_prioritized():
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    incremental = SimpleNamespace(id="incremental")
    fresh = SimpleNamespace(id="fresh")
    orchestrator.config = SimpleNamespace(sources=[fresh, incremental])
    orchestrator.repo = MagicMock()
    orchestrator.repo.get_source_state.side_effect = lambda source_id: (
        {"offset": 42} if source_id == "incremental" else {}
    )

    observed = []

    async def base_run(*args, **kwargs):
        observed.extend(source.id for source in orchestrator.config.sources)
        return {"status": "completed"}

    original = OptimizedHardenedOrchestrator.__mro__[1]._run_hardened
    OptimizedHardenedOrchestrator.__mro__[1]._run_hardened = base_run
    try:
        result = await orchestrator._run_hardened(None, True, False)
    finally:
        OptimizedHardenedOrchestrator.__mro__[1]._run_hardened = original

    assert result["status"] == "completed"
    assert observed == ["incremental", "fresh"]
    assert orchestrator.config.sources == [fresh, incremental]
