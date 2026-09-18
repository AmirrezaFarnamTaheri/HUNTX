"""Ingestion incompleteness must block the release before it is published."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huntx.core.hardened_orchestrator import HardenedOrchestrator
from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


def _base_orchestrator():
    """A hardened orchestrator whose base hook never demotes a completed run."""
    orch = object.__new__(HardenedOrchestrator)
    sources = [SimpleNamespace(id=str(i), publication_eligible=True) for i in range(3)]
    route = SimpleNamespace(name="route", formats=["npvt"], from_sources=["0"], destinations=[])
    orch.config = SimpleNamespace(sources=sources, routes=[route])
    orch.max_workers = 1
    orch._get_build_window_start = MagicMock(return_value="2026-09-14 12:00:00")

    async def worker(queue, results, lock):
        results.update(ok=3, err=0)

    orch._worker_async = worker
    orch.transform_pipeline = MagicMock()
    orch.transform_pipeline.process_pending.return_value = {"completed": True}
    orch.build_pipeline = MagicMock()
    orch.build_pipeline.run.return_value = [
        {
            "route_name": "route",
            "format": "npvt",
            "artifact_hash": "fixture",
            "data": b"fixture",
        }
    ]
    orch.publish_pipeline = MagicMock()
    orch._export_outputs = MagicMock()
    orch._export_dev_outputs = MagicMock()
    orch.repo = MagicMock()
    orch.raw_store = MagicMock()
    orch.artifact_store = MagicMock()
    return orch


def test_base_hook_never_demotes_a_completed_run():
    """The hardened base has no ingestion budget, so nothing is demoted."""
    orch = _base_orchestrator()
    assert orch._ingestion_demotion_reason() is None
    summary = asyncio.run(orch._run_hardened(None, True, False))
    assert summary["release_eligible"] is True
    assert summary["status"] == "completed"
    assert summary["partial_reason"] is None
    orch._export_outputs.assert_called_once()


def test_budget_exhaustion_blocks_export_before_publication():
    """An exhausted ingestion budget must stop export, not just the summary."""
    orch = _base_orchestrator()
    # Simulate the optimized runtime's budget signal on the hardened base.
    orch._ingestion_demotion_reason = lambda: "ingestion_budget_exhausted"
    summary = asyncio.run(orch._run_hardened(None, True, False))
    assert summary["release_eligible"] is False
    assert summary["status"] == "partial"
    assert summary["partial_reason"] == "ingestion_budget_exhausted"
    orch.publish_pipeline.run.assert_not_called()
    orch._export_outputs.assert_not_called()


def test_residue_remaining_blocks_export_before_publication():
    """Leftover queue residue must stop export the same way."""
    orch = _base_orchestrator()
    orch._ingestion_demotion_reason = lambda: "ingestion_residue_remaining"
    summary = asyncio.run(orch._run_hardened(None, True, False))
    assert summary["release_eligible"] is False
    assert summary["status"] == "partial"
    assert summary["partial_reason"] == "ingestion_residue_remaining"
    orch._export_outputs.assert_not_called()


def test_demotion_still_allows_dev_export_when_partial_export_enabled():
    """A demoted run may keep diagnostic dev output, never the public one."""
    orch = _base_orchestrator()
    orch._ingestion_demotion_reason = lambda: "ingestion_budget_exhausted"
    summary = asyncio.run(orch._run_hardened(None, True, allow_partial_export=True))
    assert summary["release_eligible"] is False
    orch._export_outputs.assert_not_called()
    orch._export_dev_outputs.assert_called_once()


def _optimized_scaffold(residue_remaining: int, budget_exhausted: bool):
    """Wire an optimized orchestrator with a stubbed base pipeline."""
    orch = object.__new__(OptimizedHardenedOrchestrator)
    orch._ingestion_budget_exhausted = budget_exhausted
    orch._work_queue = MagicMock()
    orch._work_queue.summary.return_value = {"remaining": residue_remaining}
    return orch


@pytest.mark.parametrize(
    "residue,budget,expected",
    [
        (0, False, None),
        (0, True, "ingestion_budget_exhausted"),
        (5, False, "ingestion_residue_remaining"),
        # Budget exhaustion takes precedence over residue when both are present.
        (5, True, "ingestion_budget_exhausted"),
    ],
)
def test_optimized_hook_reports_incompleteness(residue, budget, expected):
    orch = _optimized_scaffold(residue, budget)
    assert orch._ingestion_demotion_reason() == expected


def test_optimized_hook_tolerates_missing_work_queue():
    """A partially-constructed instance must not raise on the hook."""
    orch = object.__new__(OptimizedHardenedOrchestrator)
    orch._ingestion_budget_exhausted = False
    # No _work_queue attribute set; the hook must fail open to None, not raise.
    assert orch._ingestion_demotion_reason() is None
