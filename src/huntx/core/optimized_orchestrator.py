from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from .hardened_orchestrator import HardenedOrchestrator
from ..pipeline.optimized_transform import OptimizedTransformPipeline

logger = logging.getLogger(__name__)


class OptimizedHardenedOrchestrator(HardenedOrchestrator):
    """Hardened runner with source isolation and adaptive transformation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.transform_pipeline = OptimizedTransformPipeline(
            self.raw_store,
            self.repo,
            self.registry,
            {source.id: source for source in self.config.sources},
            max_workers=self.max_workers,
        )

    def _source_timeout(self) -> float:
        raw = os.environ.get("HUNTX_SOURCE_TIMEOUT", "600")
        try:
            return max(30.0, min(float(raw), 1800.0))
        except ValueError:
            logger.warning("Invalid HUNTX_SOURCE_TIMEOUT=%r; using 600", raw)
            return 600.0

    async def _worker_async(
        self,
        source_queue: asyncio.Queue[Any],
        results: dict[str, int],
        lock: asyncio.Lock,
    ) -> None:
        timeout = self._source_timeout()
        while True:
            try:
                source = source_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            success = False
            try:
                success = bool(
                    await asyncio.wait_for(
                        self._ingest_one_source_async(source),
                        timeout=timeout,
                    )
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[Worker] Source %s exceeded %.1fs and was isolated",
                    source.id,
                    timeout,
                )
            except Exception:
                logger.exception("[Worker] Source %s failed", source.id)
            finally:
                async with lock:
                    results["ok" if success else "err"] += 1
                source_queue.task_done()

    async def _run_hardened(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        original = list(self.config.sources)

        def priority(source: Any) -> tuple[int, str]:
            try:
                state = self.repo.get_source_state(source.id) or {}
                offset = int(state.get("offset", 0) or 0)
            except Exception:
                offset = 0
            return (0 if offset > 0 else 1, str(source.id))

        self.config.sources = sorted(original, key=priority)
        try:
            return await super()._run_hardened(*args, **kwargs)
        finally:
            self.config.sources = original
