"""Recoverable ingestion is not permission to replace the public snapshot."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huntx.core.hardened_orchestrator import HardenedOrchestrator


def make_orchestrator(*, errors=0, empty=False, build_failure=False):
    orch = object.__new__(HardenedOrchestrator)
    sources = [SimpleNamespace(id=str(i), publication_eligible=True) for i in range(3)]
    route = SimpleNamespace(name="route", formats=["npvt"], from_sources=["0"], destinations=[])
    orch.config = SimpleNamespace(sources=sources, routes=[route])
    orch.max_workers = 1
    orch._get_build_window_start = MagicMock(return_value="2026-09-14 12:00:00")

    async def worker(queue, results, lock):
        results.update(ok=3 - errors, err=errors)

    orch._worker_async = worker
    orch.transform_pipeline = MagicMock()
    orch.transform_pipeline.process_pending.return_value = {"completed": True}
    orch.build_pipeline = MagicMock()
    orch.build_pipeline.run.return_value = [] if empty else [{
        "route_name": "route", "format": "npvt", "artifact_hash": "fixture", "data": b"fixture",
    }]
    if build_failure:
        orch.build_pipeline.run.side_effect = RuntimeError("database unavailable")
    orch.publish_pipeline = MagicMock()
    orch._export_outputs = MagicMock()
    orch._export_dev_outputs = MagicMock()
    orch.repo = MagicMock()
    orch.raw_store = MagicMock()
    orch.artifact_store = MagicMock()
    return orch


@pytest.mark.parametrize("errors,build_failure", [(1, False), (0, True)])
def test_recoverable_failure_never_publishes_or_replaces_snapshot(errors, build_failure):
    orch = make_orchestrator(errors=errors, build_failure=build_failure)
    summary = asyncio.run(orch._run_hardened(None, False, True))
    assert summary["release_eligible"] is False
    assert summary["ingest_ok"] > 0
    orch.publish_pipeline.run.assert_not_called()
    orch._export_outputs.assert_not_called()


@pytest.mark.parametrize("empty", [False, True])
def test_success_can_replace_snapshot_including_explicit_empty(empty):
    orch = make_orchestrator(empty=empty)
    summary = asyncio.run(orch._run_hardened(None, True, False))
    assert summary["release_eligible"] is True
    assert summary["min_ingested_at"] == "2026-09-14 12:00:00"
    orch._export_outputs.assert_called_once_with(orch.build_pipeline.run.return_value)
    orch._get_build_window_start.assert_called_once_with()


def test_export_failure_revokes_release_eligibility():
    orch = make_orchestrator()
    orch._export_outputs.side_effect = OSError("disk full")
    summary = asyncio.run(orch._run_hardened(None, True, False))
    assert summary["release_eligible"] is False
    assert summary["status"] == "failed"
