"""A stalled production build must leave actionable evidence without leaking URIs."""

import asyncio
import logging
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huntx.core.orchestrator import Orchestrator


def test_pending_build_emits_route_progress_and_stack_evidence(caplog):
    blocked = threading.Event()
    started = threading.Event()
    orchestrator = Orchestrator.__new__(Orchestrator)
    source = SimpleNamespace(id="approved", publication_eligible=True)
    route = SimpleNamespace(
        name="all_sources", formats=["npvt"],
        from_sources=["approved"], destinations=[],
    )
    orchestrator.config = SimpleNamespace(sources=[source], routes=[route])
    orchestrator.max_workers = 1
    orchestrator._get_build_window_start = lambda: "2026-11-12 00:00:00"
    orchestrator._build_progress_interval_seconds = 0.025

    async def ingest(_queue, results, _lock):
        results["ok"] += 1

    orchestrator._worker_async = ingest
    orchestrator.transform_pipeline = MagicMock()
    orchestrator.transform_pipeline.process_pending.return_value = {
        "completed": True, "stop_reason": "complete",
    }
    orchestrator.build_pipeline = MagicMock()

    def blocking_build(*_args, **_kwargs):
        started.set()
        blocked.wait(timeout=1.0)
        return []

    orchestrator.build_pipeline.run.side_effect = blocking_build
    orchestrator.publish_pipeline = MagicMock()
    orchestrator._export_outputs = MagicMock()
    orchestrator._export_dev_outputs = MagicMock()
    orchestrator.raw_store = MagicMock()
    orchestrator.artifact_store = MagicMock()
    began = time.monotonic()

    try:
        with patch("faulthandler.dump_traceback") as dump:
            with caplog.at_level(logging.WARNING, logger="huntx.core.hardened_orchestrator"):
                result = asyncio.run(
                    orchestrator._run_async(
                        timeout=0.16, no_publish=True, allow_partial_export=False
                    )
                )
            assert dump.called, "A stuck build needs a thread-stack capture"
    finally:
        blocked.set()

    assert started.is_set()
    assert time.monotonic() - began < 0.65
    assert result["status"] == "timed_out"
    assert result["release_eligible"] is False
    assert result["timed_out_stage"] == "build"
    assert result["build_pending"] == 1
    assert "Build still running" in caplog.text
    assert "all_sources" in caplog.text
    assert "Build timed out" in caplog.text
    orchestrator._export_outputs.assert_not_called()
