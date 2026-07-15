import asyncio
from types import SimpleNamespace

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


def test_source_timeout_is_isolated():
    async def exercise() -> None:
        orchestrator = object.__new__(OptimizedHardenedOrchestrator)
        orchestrator._ingestion_stop_monotonic = None
        orchestrator._ingestion_budget_exhausted = False
        orchestrator._source_timeout = lambda: 0.05

        observed: list[str] = []

        async def mock_ingest(source):
            observed.append(source.id)
            if source.id == "slow-source":
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.01)
            return True

        async def no_persistent_work(*args, **kwargs):
            return None

        orchestrator._ingest_one_source_async = mock_ingest
        orchestrator._run_persistent_windows = no_persistent_work

        queue: asyncio.Queue[SimpleNamespace] = asyncio.Queue()
        queue.put_nowait(SimpleNamespace(id="slow-source", type="telegram"))
        queue.put_nowait(SimpleNamespace(id="healthy-source", type="telegram"))

        results = {"ok": 0, "err": 0}
        await orchestrator._worker_async(queue, results, asyncio.Lock())

        assert observed == ["slow-source", "healthy-source"]
        assert results == {"ok": 1, "err": 1}
        assert queue.empty()

    asyncio.run(exercise())


def test_lifo_controls_are_bounded(monkeypatch):
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator.fetch_windows = {"file_fresh_hours": 48}

    monkeypatch.setenv("HUNTX_INGEST_WINDOW_SECONDS", "1")
    monkeypatch.setenv("HUNTX_INGEST_PAGE_SIZE", "99999")
    monkeypatch.setenv("HUNTX_LIFO_LOOKBACK_HOURS", "10000")

    assert orchestrator._window_seconds() == 300
    assert orchestrator._window_page_size() == 1000
    assert orchestrator._lookback_seconds() == 30 * 24 * 3600
