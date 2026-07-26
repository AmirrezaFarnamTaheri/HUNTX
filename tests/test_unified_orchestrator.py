import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishRoute,
    PublishingConfig,
    SourceConfig,
    SourceSelector,
    TelegramSourceConfig,
)
from huntx.core.scoring import ProxyScoringEngine
from huntx.core.unified_orchestrator import UnifiedOrchestrator


def _config(*routes: PublishRoute) -> AppConfig:
    return AppConfig(
        sources=[
            SourceConfig(
                id="src_bot",
                type="telegram",
                selector=SourceSelector(include_formats=["fmt"]),
                telegram=TelegramSourceConfig(token="123:bot_token", chat_id="123"),
            )
        ],
        publishing=PublishingConfig(routes=list(routes)),
    )


def _route(name: str) -> PublishRoute:
    return PublishRoute(
        name=name,
        from_sources=["src_bot"],
        formats=["fmt"],
        destinations=[DestinationConfig(chat_id="dest1", mode="telegram", caption_template="cap")],
    )


def _orchestrator(config: AppConfig) -> UnifiedOrchestrator:
    """Build a bounded orchestration harness without external I/O."""
    orch = UnifiedOrchestrator.__new__(UnifiedOrchestrator)
    orch.config = config
    orch.enable_benchmarking = False
    orch.max_proxy_latency_ms = 1500
    orch.min_proxy_quality_score = 25.0
    orch.scoring_engine = ProxyScoringEngine()
    orch.repo = MagicMock()
    orch.transform_pipeline = MagicMock()
    orch.transform_pipeline.process_pending.return_value = {"processed": 0, "failed": 0}
    orch.build_pipeline = MagicMock()
    orch.publish_pipeline = MagicMock()
    orch._canonical_ingestion_sources = AsyncMock(return_value=list(config.sources))
    orch._run_ingestion = AsyncMock(return_value=None)
    orch._get_seen_file_max_id = MagicMock(return_value=0)
    orch._deadline = None
    return orch


def test_unified_orchestrator_run_is_bounded_and_completes() -> None:
    route = _route("route1")
    orch = _orchestrator(_config(route))
    orch.repo.get_records_for_build.return_value = []
    orch.build_pipeline.run.return_value = [SimpleNamespace(route_name="route1")]

    result = asyncio.run(orch.run_async(no_publish=True))

    assert result["status"] == "completed"
    assert result["unified"] is True
    assert result["results"] == {"ok": 1, "err": 0}
    orch._run_ingestion.assert_awaited_once()
    orch.publish_pipeline.run.assert_not_called()


def test_unified_orchestrator_isolates_route_failures() -> None:
    first = _route("broken")
    second = _route("healthy")
    orch = _orchestrator(_config(first, second))
    orch.repo.get_records_for_build.return_value = []
    orch.build_pipeline.run.side_effect = [RuntimeError("broken route"), [SimpleNamespace(route_name="healthy")]]

    result = asyncio.run(orch.run_async(no_publish=True))

    assert result["status"] == "completed_with_errors"
    assert result["results"] == {"ok": 1, "err": 1}
    assert orch.build_pipeline.run.call_count == 2


def test_prepare_route_records_keeps_passthrough_and_high_scores() -> None:
    route = _route("route1")
    orch = _orchestrator(_config(route))
    low = {"record_type": "fmt", "data": {"line": "vless://low", "latency_ms": 900}}
    high = {"record_type": "fmt", "data": {"line": "vless://high", "latency_ms": 25}}
    passthrough = {"record_type": "fmt", "data": {"payload": "opaque"}}
    orch.repo.get_records_for_build.return_value = [low, passthrough, high]
    orch.scoring_engine = MagicMock()
    orch.scoring_engine.score_proxy.side_effect = [10.0, 90.0]
    results = {"ok": 0, "err": 0}

    records = asyncio.run(orch._prepare_route_records(route, 0, results))

    assert records[0] == passthrough
    assert len(records) == 2
    assert records[1]["data"]["line"] == "vless://high"
    assert records[1]["data"]["quality_score"] == 90.0
    assert results == {"ok": 0, "err": 0}
