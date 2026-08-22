import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator
from huntx.core.runtime_resilience import apply_runtime_resilience
from huntx.pipeline.windowed_ingest import WindowedIngestionPipeline

apply_runtime_resilience()


def _telegram_source(source_id: str, peer: str):
    config = SimpleNamespace(
        api_id=1,
        api_hash="hash",
        session="session",
        peer=peer,
    )
    return SimpleNamespace(id=source_id, type="telegram_user", telegram_user=config)


def test_numeric_canonicalization_checks_reachability_once_and_deduplicates(monkeypatch):
    instances = []

    class ReachableConnector:
        def __init__(self, *, peer, **kwargs):
            self.peer = peer
            self.resolve_calls = 0
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_channel_id_async(self):
            self.resolve_calls += 1
            return 42

    monkeypatch.setattr(
        "huntx.core.optimized_orchestrator.WindowedTelegramUserConnector",
        ReachableConnector,
    )
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._work_queue = MagicMock()
    orchestrator._ingestion_stop_monotonic = None
    orchestrator._ingestion_budget_exhausted = False

    accepted = asyncio.run(
        orchestrator._canonical_ingestion_sources(
            [
                _telegram_source("primary", "-10042"),
                _telegram_source("alias", "-10042"),
            ]
        )
    )

    assert [source.id for source in accepted] == ["primary"]
    assert len(instances) == 1
    assert instances[0].resolve_calls == 1
    orchestrator._work_queue.terminalize_source.assert_called_once()
    assert orchestrator._work_queue.terminalize_source.call_args.args[0] == "alias"


def test_canonical_timeout_preserves_source(monkeypatch):
    class SlowConnector:
        def __init__(self, *, peer, **kwargs):
            self.peer = peer

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_channel_id_async(self):
            await asyncio.sleep(1)
            return 42

    monkeypatch.setenv("HUNTX_CANONICAL_RESOLVE_TIMEOUT", "0.05")
    monkeypatch.setattr(
        "huntx.core.optimized_orchestrator.WindowedTelegramUserConnector",
        SlowConnector,
    )
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._work_queue = MagicMock()
    orchestrator._ingestion_stop_monotonic = None
    orchestrator._ingestion_budget_exhausted = False

    source = _telegram_source("username", "@channel")
    accepted = asyncio.run(orchestrator._canonical_ingestion_sources([source]))

    assert accepted == [source]
    orchestrator._work_queue.terminalize_source.assert_not_called()


def test_preflight_time_is_removed_from_base_timeout(monkeypatch):
    async def exercise() -> float:
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
        orchestrator._work_queue.summary.return_value = {"remaining": 0}
        orchestrator._windowed_ingestion = SimpleNamespace(close=AsyncMock())
        orchestrator._completion_buffer = lambda timeout: 0.0
        orchestrator._lookback_seconds = lambda: 3600
        orchestrator._window_seconds = lambda: 3600

        async def canonical(sources):
            await asyncio.sleep(0.05)
            return sources

        orchestrator._canonical_ingestion_sources = canonical
        captured: dict[str, float] = {}

        async def base_run(self, timeout, *args, **kwargs):
            captured["timeout"] = float(timeout)
            return {"status": "completed", "duration_seconds": 0.0}

        parent = OptimizedHardenedOrchestrator.__mro__[1]
        monkeypatch.setattr(parent, "_run_hardened", base_run)
        await orchestrator._run_hardened(1.0, True, False)
        return captured["timeout"]

    remaining = asyncio.run(exercise())
    assert 0.0 < remaining < 0.98


def test_window_pipeline_reuses_connector(monkeypatch):
    instances = []

    class FakeConnector:
        def __init__(self, *, peer, **kwargs):
            self.peer = peer
            self.deadline = None
            self.enters = 0
            self.exits = 0
            instances.append(self)

        async def __aenter__(self):
            self.enters += 1
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.exits += 1

        async def fetch_window_page(self, **kwargs):
            return SimpleNamespace(
                items=[],
                continuation_cursor=None,
                completed=True,
                scanned_messages=0,
            )

    monkeypatch.setattr(
        "huntx.pipeline.windowed_ingest.WindowedTelegramUserConnector",
        FakeConnector,
    )

    class DB:
        @contextmanager
        def connect(self):
            yield object()

    ingestion = SimpleNamespace(
        state_repo=SimpleNamespace(db=DB()),
        _process_batch=lambda *args, **kwargs: (0, 0, 0, 0, 0),
    )
    queue = MagicMock()
    pipeline = WindowedIngestionPipeline(ingestion, queue)
    item = SimpleNamespace(
        id=1,
        source_id="source",
        window_start_ts=0,
        window_end_ts=3600,
        continuation_cursor=None,
        lease_token="lease-token",
    )

    async def exercise():
        await pipeline.run_page(
            _telegram_source("source", "@one"),
            item,
            owner="owner",
            deadline=None,
            page_size=100,
        )
        await pipeline.run_page(
            _telegram_source("source", "@two"),
            item,
            owner="owner",
            deadline=None,
            page_size=100,
        )
        await pipeline.close()

    asyncio.run(exercise())
    assert len(instances) == 1
    assert instances[0].enters == 1
    assert instances[0].exits == 1
    assert queue.checkpoint_page.call_count == 2
