"""Ingestion incompleteness must block the release before it is published."""

import asyncio
import threading
import time
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
    # Missing queue state cannot prove a complete ingestion; fail closed.
    assert orch._ingestion_demotion_reason() == "ingestion_state_unavailable"


def _required_destination():
    return SimpleNamespace(
        chat_id="123",
        mode="telegram",
        caption_template="Update",
        token="test-publication-token",
        required=True,
    )


def test_false_publisher_result_cannot_authorize_a_release():
    """A returned False means zero verified deliveries, not success."""
    orch = _base_orchestrator()
    orch.config.routes[0].destinations = [_required_destination()]
    orch.publish_pipeline.run.return_value = False

    summary = asyncio.run(orch._run_hardened(None, False, False))

    assert summary["publish_failures"] == 1
    assert summary["status"] == "partial"
    assert summary["release_eligible"] is False
    orch._export_outputs.assert_not_called()


def test_hardened_publisher_timeout_returns_without_waiting_for_stalled_thread():
    """A hung publisher must not consume an unbounded extra shutdown wait."""
    orch = _base_orchestrator()
    orch.config.routes[0].destinations = [_required_destination()]
    release = threading.Event()

    def stalled_publish(*_args, **_kwargs):
        release.wait(timeout=2.0)
        return True

    orch.publish_pipeline.run.side_effect = stalled_publish
    started = time.monotonic()
    try:
        summary = asyncio.run(orch._run_hardened(0.18, False, False))
    finally:
        release.set()
    elapsed = time.monotonic() - started

    assert elapsed < 0.55, f"deadline added a blocking publisher shutdown: {elapsed:.3f}s"
    assert summary["status"] == "timed_out"
    assert summary["release_eligible"] is False
    orch._export_outputs.assert_not_called()


class _ControllableDeadline:
    """Deterministic deadline triggered by a chosen synchronous operation."""

    def __init__(self):
        self.expired_now = False

    def remaining_seconds(self):
        return 0.0 if self.expired_now else 5.0

    def expired(self):
        return self.expired_now

    def raise_if_expired(self, stage="operation"):
        from huntx.core.deadline import DeadlineExceeded

        if self.expired_now:
            raise DeadlineExceeded("deadline exceeded during " + stage)


def test_export_overrunning_deadline_never_reports_completed(monkeypatch):
    """Even successful disk writes cannot authorize an expired release."""
    orch = _base_orchestrator()
    deadline = _ControllableDeadline()
    monkeypatch.setattr("huntx.core.hardened_orchestrator.Deadline", lambda _timeout: deadline)
    orch._export_outputs.side_effect = lambda _results: setattr(deadline, "expired_now", True)

    summary = asyncio.run(orch._run_hardened(10.0, True, False))

    assert summary["status"] == "timed_out"
    assert summary["timed_out_stage"] == "export"
    assert summary["release_eligible"] is False
    orch._export_dev_outputs.assert_not_called()


def test_cleanup_deadline_stops_remaining_mutations(monkeypatch):
    """Slow archive cleanup must not create a false completed outcome."""
    orch = _base_orchestrator()
    deadline = _ControllableDeadline()
    monkeypatch.setattr("huntx.core.hardened_orchestrator.Deadline", lambda _timeout: deadline)
    orch.raw_store.prune_processed.side_effect = lambda _repo: setattr(deadline, "expired_now", True)

    summary = asyncio.run(orch._run_hardened(10.0, True, False))

    assert summary["status"] == "timed_out"
    assert summary["timed_out_stage"] == "cleanup"
    assert summary["release_eligible"] is False
    orch.raw_store.prune_orphans.assert_not_called()
    orch.artifact_store.prune_archive.assert_not_called()
