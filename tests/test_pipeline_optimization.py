import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_non_finite_lifo_lookback_falls_back(monkeypatch):
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator.fetch_windows = {"file_fresh_hours": 12}

    for value in ("nan", "inf", "-inf"):
        monkeypatch.setenv("HUNTX_LIFO_LOOKBACK_HOURS", value)
        assert orchestrator._lookback_seconds() == 12 * 3600


def test_canonical_channel_alias_is_not_seeded(monkeypatch):
    class FakeConnector:
        def __init__(self, *, peer, **kwargs):
            self.peer = peer

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_channel_id_async(self):
            return {"primary": 42, "alias": 42}[self.peer]

    monkeypatch.setattr(
        "huntx.core.optimized_orchestrator.WindowedTelegramUserConnector",
        FakeConnector,
    )
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._work_queue = MagicMock()
    def config(peer):
        return SimpleNamespace(
            api_id=1,
            api_hash="hash",
            session="session",
            peer=peer,
        )
    sources = [
        SimpleNamespace(id="primary", type="telegram_user", telegram_user=config("primary")),
        SimpleNamespace(id="alias", type="telegram_user", telegram_user=config("alias")),
    ]

    accepted = asyncio.run(orchestrator._canonical_ingestion_sources(sources))

    assert [source.id for source in accepted] == ["primary"]
    orchestrator._work_queue.terminalize_source.assert_called_once()
    assert orchestrator._work_queue.terminalize_source.call_args.args[0] == "alias"


def test_residue_is_budget_skipped_only_after_budget_exhaustion():
    async def exercise(exhausted: bool) -> int:
        orchestrator = object.__new__(OptimizedHardenedOrchestrator)
        orchestrator.config = SimpleNamespace(sources=[])
        orchestrator._work_queue = MagicMock()
        orchestrator._work_queue.recover_expired_leases.return_value = 0
        orchestrator._work_queue.seed_rolling_horizon.return_value = {
            "campaign_id": 1,
            "anchor_ts": 7200,
            "target_start_ts": 3600,
            "inserted": 0,
        }
        orchestrator._work_queue.release_owner.return_value = 0
        orchestrator._work_queue.summary.return_value = {"pending": 4, "remaining": 4}
        orchestrator._completion_buffer = lambda timeout: 0.0
        orchestrator._lookback_seconds = lambda: 3600
        orchestrator._window_seconds = lambda: 3600

        async def canonical(sources):
            return sources

        orchestrator._canonical_ingestion_sources = canonical

        async def base_run(*args, **kwargs):
            orchestrator._ingestion_budget_exhausted = exhausted
            return {"status": "completed"}

        parent = OptimizedHardenedOrchestrator.__mro__[1]
        original = parent._run_hardened
        parent._run_hardened = base_run
        try:
            result = await orchestrator._run_hardened(None, True, False)
        finally:
            parent._run_hardened = original
        return int(result["ingest_skipped_due_to_budget"])

    assert asyncio.run(exercise(False)) == 0
    assert asyncio.run(exercise(True)) == 4
