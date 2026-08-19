from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from huntx.core.hardened_orchestrator import HardenedOrchestrator
from huntx.core import runtime_resilience


@pytest.mark.asyncio
async def test_resilient_runtime_filters_before_queue_seed_and_restores_config():
    approved = SimpleNamespace(id="approved", publication_eligible=True)
    candidate = SimpleNamespace(id="candidate", publication_eligible=False)
    config = SimpleNamespace(sources=[approved, candidate])

    queue = MagicMock()
    queue.recover_expired_leases.return_value = 0
    queue.seed_rolling_horizon.return_value = {
        "campaign_id": 1,
        "anchor_ts": 2,
        "target_start_ts": 3,
        "inserted": 4,
    }
    queue.summary.return_value = {"remaining": 0}
    queue.release_owner.return_value = 0
    queue.terminalize_source.return_value = 2

    orchestrator = SimpleNamespace(
        config=config,
        _work_queue=queue,
        _windowed_ingestion=None,
        _completion_buffer=lambda timeout: 0.0,
        _lookback_seconds=lambda: 3600,
        _window_seconds=lambda: 600,
        _canonical_ingestion_sources=AsyncMock(return_value=[approved]),
    )

    with patch.object(
        HardenedOrchestrator,
        "_run_hardened",
        new=AsyncMock(return_value={"status": "completed", "duration_seconds": 1.0}),
    ) as run_hardened:
        summary = await runtime_resilience._run_hardened(
            orchestrator,
            timeout=30,
            no_publish=True,
            allow_partial_export=False,
        )

    orchestrator._canonical_ingestion_sources.assert_awaited_once_with([approved])
    queue.terminalize_source.assert_called_once_with(
        "candidate",
        "source is not publication-approved",
    )
    seeded_sources = queue.seed_rolling_horizon.call_args.args[0]
    assert seeded_sources == [approved]
    run_hardened.assert_awaited_once()
    assert run_hardened.await_args.args[0] is orchestrator
    assert config.sources == [approved, candidate]
    assert summary["configured_approved_sources"] == 1
    assert summary["excluded_sources"] == 1
    assert summary["canonical_ingestion_sources"] == 1


@pytest.mark.asyncio
async def test_disabled_legacy_runtime_fails_closed():
    with pytest.raises(RuntimeError, match="disabled"):
        await runtime_resilience._disabled_legacy_run()
