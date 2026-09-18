from types import SimpleNamespace
from unittest.mock import patch

import pytest

from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishingConfig,
    PublishRoute,
    SourceConfig,
    SourceSelector,
    TelegramSourceConfig,
)
from huntx.core import runtime_resilience
from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator
from huntx.core.unified_orchestrator import UnifiedOrchestrator
from huntx.pipeline.governed_build import GovernedBuildPipeline
from huntx.store import paths


def test_unified_orchestrator_is_a_production_runtime_facade():
    assert issubclass(UnifiedOrchestrator, OptimizedHardenedOrchestrator)


@patch("huntx.core.unified_orchestrator.wire_production_governance")
@patch("huntx.core.unified_orchestrator.apply_runtime_resilience")
@patch.object(OptimizedHardenedOrchestrator, "__init__", return_value=None)
@patch.object(
    OptimizedHardenedOrchestrator,
    "run",
    return_value={"status": "completed", "duration_seconds": 1.25},
)
def test_unified_orchestrator_delegates_run_contract(mock_run, mock_init, _mock_apply, mock_wire):
    # __init__ is mocked out, so the base class never assigns ``config``.
    with patch.object(UnifiedOrchestrator, "config", object(), create=True):
        orchestrator = UnifiedOrchestrator(
            object(),
            enable_benchmarking=True,
            max_proxy_latency_ms=1200,
        )

    result = orchestrator.run(
        timeout=30,
        no_publish=True,
        allow_partial_export=True,
    )

    mock_init.assert_called_once()
    mock_run.assert_called_once_with(
        timeout=30,
        no_publish=True,
        allow_partial_export=True,
    )
    assert result["status"] == "completed"
    assert result["unified"] is True
    assert result["elapsed_seconds"] == 1.25
    assert orchestrator.enable_benchmarking is True
    assert orchestrator.max_proxy_latency_ms == 1200
    assert hasattr(orchestrator, "circuit_breaker")
    assert hasattr(orchestrator, "scoring_engine")
    assert hasattr(orchestrator, "streaming_parser")
    assert hasattr(orchestrator, "geo_routing")
    assert hasattr(orchestrator, "self_healing")


def _config() -> AppConfig:
    return AppConfig(
        sources=[
            SourceConfig(
                id="src",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123:tok", chat_id="-1001"),
            )
        ],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="route",
                    from_sources=["src"],
                    formats=["npvt"],
                    destinations=[DestinationConfig(chat_id="-1002", token="123:pub")],
                )
            ]
        ),
    )


@patch("huntx.core.unified_orchestrator.wire_production_governance")
@patch("huntx.core.unified_orchestrator.apply_runtime_resilience")
def test_unified_orchestrator_installs_the_production_contract_around_construction(mock_apply, mock_wire):
    """The runtime overrides must exist before construction, the governed wiring after."""
    order: list[str] = []
    mock_apply.side_effect = lambda: order.append("apply")
    mock_wire.side_effect = lambda *_a, **_k: order.append("wire")

    def fake_init(self, *_args, **_kwargs):
        order.append("init")
        self.config = SimpleNamespace(marker=True)

    with patch.object(OptimizedHardenedOrchestrator, "__init__", fake_init):
        orchestrator = UnifiedOrchestrator(object())

    assert order == ["apply", "init", "wire"]
    mock_wire.assert_called_once_with(orchestrator, orchestrator.config)


@pytest.fixture
def isolated_runtime_paths(tmp_path):
    original = paths.current_paths()
    paths.set_paths(str(tmp_path / "data"), str(tmp_path / "data" / "state.db"))
    try:
        yield
    finally:
        paths.set_paths(str(original.data_dir), str(original.state_db_path))


def test_public_unified_orchestrator_matches_production_behaviour(isolated_runtime_paths):
    """Regression: ``huntx.UnifiedOrchestrator`` used to skip every production patch.

    Only the CLI factory installed the resilient runtime and the governed build
    pipeline, so a library caller using the documented public facade ran an
    ungoverned pipeline. Built for real (no mocks), the facade must now carry
    the same effective methods and the same governed build stage the factory
    produces.
    """
    orchestrator = UnifiedOrchestrator(_config(), max_workers=1)

    assert getattr(OptimizedHardenedOrchestrator, "_runtime_resilience_applied", False)
    assert type(orchestrator)._run_hardened is runtime_resilience._run_hardened
    assert type(orchestrator)._canonical_ingestion_sources is runtime_resilience._canonical_ingestion_sources
    assert isinstance(orchestrator.build_pipeline, GovernedBuildPipeline)
    assert callable(orchestrator._export_outputs)
