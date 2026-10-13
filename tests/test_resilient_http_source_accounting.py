"""HTTP feed diagnostics must survive the active resilient orchestration override.

The production runtime monkeypatches OptimizedHardenedOrchestrator._run_hardened
with runtime_resilience._run_hardened. Its historical implementation omitted
initialization and attachment of the HTTP feed ledger, so all feeds appeared
'not_observed' despite real successful and failed retrieval attempts.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from huntx.core.hardened_orchestrator import HardenedOrchestrator
from huntx.core import runtime_resilience


def _orchestrator():
    source = SimpleNamespace(
        id="http-one", type="http_subscription", publication_eligible=True
    )
    queue = MagicMock()
    queue.recover_expired_leases.return_value = 0
    queue.seed_rolling_horizon.return_value = {
        "campaign_id": 7,
        "anchor_ts": 1234,
        "target_start_ts": 1000,
        "inserted": 0,
    }
    queue.release_owner.return_value = 0
    queue.summary.return_value = {"remaining": 0}
    runner = SimpleNamespace(
        config=SimpleNamespace(sources=[source]),
        _work_queue=queue,
        _windowed_ingestion=None,
        _completion_buffer=lambda timeout: 0.0,
        _lookback_seconds=lambda: 3600,
        _window_seconds=lambda: 600,
        _canonical_ingestion_sources=AsyncMock(return_value=[source]),
        _reset_investigation_metrics=MagicMock(),
        _investigation_metrics=MagicMock(return_value={
            "sources_checked": 1, "messages_scanned": 0,
            "messages_new": 0, "cursor_updates": 0,
        }),
    )
    return runner


@pytest.mark.asyncio
async def test_resilient_runtime_initializes_and_publishes_http_feed_evidence():
    runner = _orchestrator()

    async def base_run(instance, _timeout, _no_publish, _allow_partial):
        # Actual feed workers record into this mutable ledger. A missing
        # ledger silently loses per-source evidence.
        assert isinstance(instance._http_source_reports, dict)
        instance._http_source_reports["http-one"] = {
            "status": "failed",
            "error_type": "TimeoutError",
            "availability": {"failures": 2, "successes": 5},
        }
        return {"status": "completed", "duration_seconds": 0.4}

    with patch.object(HardenedOrchestrator, "_run_hardened", new=base_run):
        summary = await runtime_resilience._run_hardened(
            runner, timeout=15, no_publish=True, allow_partial_export=False,
        )
    assert summary["http_sources_checked"] == 1
    assert summary["http_sources_failed"] == 1
    assert summary["http_sources_infrastructure_errors"] == 0
    assert summary["http_nodes_observed"] == 0
    assert summary["http_source_health"]["http-one"]["status"] == "failed"
    assert summary["lifo_campaign_id"] == 7


@pytest.mark.asyncio
async def test_resilient_runtime_distinguishes_success_and_infrastructure_error():
    runner = _orchestrator()

    async def base_run(instance, _timeout, _no_publish, _allow_partial):
        instance._http_source_reports["ok"] = {
            "status": "parsed", "nodes": 120, "policy_bound": 3,
            "availability": {"successes": 8, "failures": 1},
        }
        instance._http_source_reports["infra"] = {
            "status": "infrastructure_error",
            "error_type": "GoFeedWorkerUnavailable",
        }
        return {"status": "completed", "duration_seconds": 0.2}

    with patch.object(HardenedOrchestrator, "_run_hardened", new=base_run):
        summary = await runtime_resilience._run_hardened(
            runner, timeout=15, no_publish=True, allow_partial_export=False,
        )
    assert summary["http_sources_checked"] == 2
    assert summary["http_sources_failed"] == 0
    assert summary["http_sources_infrastructure_errors"] == 1
    assert summary["http_nodes_observed"] == 120
    assert summary["http_policy_bound_profiles"] == 3


@pytest.mark.asyncio
async def test_http_source_evidence_is_cleared_between_resilient_runs():
    runner = _orchestrator()
    runner._http_source_reports = {
        "stale-feed": {"status": "parsed", "nodes": 9999}
    }
    with patch.object(
        HardenedOrchestrator, "_run_hardened",
        new=AsyncMock(return_value={"status": "completed", "duration_seconds": 0.1}),
    ):
        summary = await runtime_resilience._run_hardened(
            runner, timeout=15, no_publish=True, allow_partial_export=False,
        )
    assert summary["http_sources_checked"] == 0
    assert summary["http_nodes_observed"] == 0
    assert "stale-feed" not in summary["http_source_health"]
