from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from .hardened_orchestrator import HardenedOrchestrator
from ..pipeline.optimized_transform import OptimizedTransformPipeline

logger = logging.getLogger(__name__)


class OptimizedHardenedOrchestrator(HardenedOrchestrator):
    """Hardened runner with source isolation and reserved completion time."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.transform_pipeline = OptimizedTransformPipeline(
            self.raw_store,
            self.repo,
            self.registry,
            {source.id: source for source in self.config.sources},
            max_workers=self.max_workers,
        )
        self._ingestion_stop_monotonic: Optional[float] = None
        self._ingestion_budget_exhausted = False
        self._completion_buffer_seconds = 0.0

    def _source_timeout(self) -> float:
        raw = os.environ.get("HUNTX_SOURCE_TIMEOUT", "600")
        try:
            return max(30.0, min(float(raw), 1800.0))
        except ValueError:
            logger.warning("Invalid HUNTX_SOURCE_TIMEOUT=%r; using 600", raw)
            return 600.0

    def _completion_buffer(self, timeout: Optional[float]) -> float:
        if timeout is None or timeout <= 0:
            return 0.0
        raw = os.environ.get("HUNTX_COMPLETION_BUFFER", "1800")
        try:
            requested = float(raw)
        except ValueError:
            logger.warning("Invalid HUNTX_COMPLETION_BUFFER=%r; using 1800", raw)
            requested = 1800.0
        return max(0.0, min(requested, max(0.0, timeout - 60.0)))

    async def _worker_async(
        self,
        source_queue: asyncio.Queue[Any],
        results: dict[str, int],
        lock: asyncio.Lock,
    ) -> None:
        configured_timeout = self._source_timeout()
        while True:
            stop = self._ingestion_stop_monotonic
            if stop is not None:
                remaining_budget = stop - time.monotonic()
                if remaining_budget <= 0:
                    self._ingestion_budget_exhausted = True
                    return
                source_timeout = min(configured_timeout, remaining_budget)
            else:
                remaining_budget = None
                source_timeout = configured_timeout

            try:
                source = source_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            success = False
            try:
                success = bool(
                    await asyncio.wait_for(
                        self._ingest_one_source_async(source),
                        timeout=source_timeout,
                    )
                )
            except asyncio.TimeoutError:
                if remaining_budget is not None and source_timeout < configured_timeout:
                    self._ingestion_budget_exhausted = True
                    logger.warning(
                        "[Worker] Ingestion budget reached while processing %s; "
                        "continuing with downstream stages",
                        source.id,
                    )
                else:
                    logger.error(
                        "[Worker] Source %s exceeded %.1fs and was isolated",
                        source.id,
                        source_timeout,
                    )
            except Exception:
                logger.exception("[Worker] Source %s failed", source.id)
            finally:
                async with lock:
                    results["ok" if success else "err"] += 1
                source_queue.task_done()

    async def _run_hardened(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        original = list(self.config.sources)
        self._ingestion_budget_exhausted = False
        self._completion_buffer_seconds = self._completion_buffer(timeout)
        if timeout is not None:
            ingestion_budget = max(0.0, timeout - self._completion_buffer_seconds)
            self._ingestion_stop_monotonic = time.monotonic() + ingestion_budget
        else:
            ingestion_budget = None
            self._ingestion_stop_monotonic = None

        def priority(source: Any) -> tuple[int, str]:
            try:
                state = self.repo.get_source_state(source.id) or {}
                offset = int(state.get("offset", 0) or 0)
            except Exception:
                offset = 0
            return (0 if offset > 0 else 1, str(source.id))

        self.config.sources = sorted(original, key=priority)
        logger.info(
            "[Orchestrator] budgets total=%s ingestion=%s completion_buffer=%s",
            timeout,
            ingestion_budget,
            self._completion_buffer_seconds,
        )
        try:
            summary = await super()._run_hardened(
                timeout,
                no_publish,
                allow_partial_export,
            )
        finally:
            self.config.sources = original
            self._ingestion_stop_monotonic = None

        skipped = max(
            0,
            int(summary.get("approved_sources", 0))
            - int(summary.get("ingest_ok", 0))
            - int(summary.get("ingest_err", 0)),
        )
        summary["completion_buffer_seconds"] = self._completion_buffer_seconds
        summary["ingestion_budget_seconds"] = ingestion_budget
        summary["ingestion_budget_exhausted"] = self._ingestion_budget_exhausted
        summary["ingest_skipped_due_to_budget"] = skipped
        if self._ingestion_budget_exhausted and summary.get("status") == "completed":
            summary["status"] = "partial"
        if self._ingestion_budget_exhausted:
            summary["partial_reason"] = "ingestion_budget_exhausted"
        logger.info("[Orchestrator] optimized final summary=%s", summary)
        return summary
