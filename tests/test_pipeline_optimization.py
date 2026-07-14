import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def test_source_timeout_is_isolated(monkeypatch):
    async def exercise() -> None:
        orchestrator = object.__new__(OptimizedHardenedOrchestrator)

        # Initialize required attributes that would normally be set in __init__
        orchestrator._ingestion_stop_monotonic = None
        orchestrator._ingestion_budget_exhausted = False

        # Stub _source_timeout to return a short duration (0.05s)
        orchestrator._source_timeout = lambda: 0.05

        # Mock _ingest_one_source_async to sleep based on source id
        async def mock_ingest(source):
            if source.id == "slow-source":
                # Sleep longer than timeout to trigger asyncio.wait_for TimeoutError
                await asyncio.sleep(0.2)
                return True
            else:
                # Healthy source completes quickly
                await asyncio.sleep(0.01)
                return True

        orchestrator._ingest_one_source_async = mock_ingest

        queue: asyncio.Queue[SimpleNamespace] = asyncio.Queue()
        queue.put_nowait(SimpleNamespace(id="slow-source"))
        queue.put_nowait(SimpleNamespace(id="healthy-source"))

        results = {"ok": 0, "err": 0}
        await orchestrator._worker_async(queue, results, asyncio.Lock())

        # Assert one error (slow source timed out) and one success (healthy source)
        assert results == {"ok": 1, "err": 1}
        # Assert queue is fully drained
        assert queue.empty()

    asyncio.run(exercise())


def test_incremental_sources_are_prioritized():
    async def exercise() -> None:
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

        parent = OptimizedHardenedOrchestrator.__mro__[1]
        original = parent._run_hardened
        parent._run_hardened = base_run
        try:
            result = await orchestrator._run_hardened(None, True, False)
        finally:
            parent._run_hardened = original

        assert result["status"] == "completed"
        assert observed == ["incremental", "fresh"]
        assert orchestrator.config.sources == [fresh, incremental]

    asyncio.run(exercise())
