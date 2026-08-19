from unittest.mock import patch

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator
from huntx.core.unified_orchestrator import UnifiedOrchestrator


def test_unified_orchestrator_is_a_production_runtime_facade():
    assert issubclass(UnifiedOrchestrator, OptimizedHardenedOrchestrator)


@patch.object(OptimizedHardenedOrchestrator, "__init__", return_value=None)
@patch.object(
    OptimizedHardenedOrchestrator,
    "run",
    return_value={"status": "completed", "duration_seconds": 1.25},
)
def test_unified_orchestrator_delegates_run_contract(mock_run, mock_init):
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
