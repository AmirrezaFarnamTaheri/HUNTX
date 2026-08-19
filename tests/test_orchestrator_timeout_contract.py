import asyncio
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from huntx.core.orchestrator import Orchestrator


class TestOrchestratorTimeoutContract(unittest.TestCase):
    def _orchestrator_with_blocking_publisher(
        self,
        release_publisher: threading.Event,
    ) -> Orchestrator:
        orchestrator = Orchestrator.__new__(Orchestrator)
        source = SimpleNamespace(id="source", publication_eligible=True)
        destination = SimpleNamespace(
            chat_id="123",
            mode="telegram",
            caption_template=None,
            token="token",
            required=True,
        )
        route = SimpleNamespace(
            name="route",
            formats=["npvt"],
            from_sources=["source"],
            destinations=[destination],
        )
        orchestrator.config = SimpleNamespace(sources=[source], routes=[route])
        orchestrator.max_workers = 1
        orchestrator._get_seen_file_max_id = MagicMock(return_value=0)

        async def worker(_queue, results, _lock) -> None:
            results["ok"] += 1

        orchestrator._worker_async = worker
        orchestrator.transform_pipeline = MagicMock()
        orchestrator.transform_pipeline.process_pending.return_value = {
            "completed": True,
            "stop_reason": "complete",
        }
        orchestrator.build_pipeline = MagicMock()
        orchestrator.build_pipeline.run.return_value = [
            {
                "route_name": "route",
                "artifact_hash": "a" * 64,
                "format": "npvt",
                "data": b"payload",
            }
        ]
        orchestrator.publish_pipeline = MagicMock()
        orchestrator.publish_pipeline.run.side_effect = lambda *_args: release_publisher.wait(timeout=5.0)
        orchestrator._export_outputs = MagicMock()
        orchestrator._export_dev_outputs = MagicMock()
        orchestrator.raw_store = MagicMock()
        orchestrator.artifact_store = MagicMock()
        return orchestrator

    def test_blocking_publisher_does_not_hide_timeout_or_delay_return(self) -> None:
        release_publisher = threading.Event()
        orchestrator = self._orchestrator_with_blocking_publisher(release_publisher)
        started = time.monotonic()

        try:
            summary = asyncio.run(
                orchestrator._run_async(
                    timeout=0.1,
                    no_publish=False,
                    allow_partial_export=False,
                )
            )
        finally:
            release_publisher.set()

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(summary["status"], "timed_out")
        self.assertEqual(summary["timed_out_stage"], "publishing")
        self.assertGreaterEqual(summary["publish_pending"], 1)
        self.assertIn("publish_cancelled", summary)
        orchestrator._export_outputs.assert_not_called()
        orchestrator._export_dev_outputs.assert_not_called()

    def test_partial_export_requires_explicit_opt_in(self) -> None:
        release_publisher = threading.Event()
        orchestrator = self._orchestrator_with_blocking_publisher(release_publisher)

        try:
            summary = asyncio.run(
                orchestrator._run_async(
                    timeout=0.1,
                    no_publish=False,
                    allow_partial_export=True,
                )
            )
        finally:
            release_publisher.set()

        self.assertEqual(summary["status"], "timed_out")
        self.assertTrue(summary["partial_export_enabled"])
        orchestrator._export_outputs.assert_called_once()
        orchestrator._export_dev_outputs.assert_called_once()
