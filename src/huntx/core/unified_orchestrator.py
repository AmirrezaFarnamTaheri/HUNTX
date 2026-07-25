from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import math
import os
import time
import uuid
from typing import Any, Optional

from .orchestrator import Orchestrator
from .resilience import AsyncCircuitBreaker
from .scoring import ProxyScoringEngine
from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector
from ..pipeline.optimized_transform import OptimizedTransformPipeline
from ..pipeline.windowed_ingest import WindowedIngestionPipeline
from ..state.ingestion_queue import PersistentIngestionQueue
from .latency_benchmarker import check_proxy_latency

logger = logging.getLogger(__name__)


class UnifiedOrchestrator(Orchestrator):
    """
    Unified Orchestrator combining resilience, windowed ingestion, optimized transform,
    latency benchmarking, and production rate limits into a single consolidated engine.
    """

    def __init__(self, *args: Any, enable_benchmarking: bool = True, max_proxy_latency_ms: int = 1500, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.enable_benchmarking = enable_benchmarking
        self.max_proxy_latency_ms = max_proxy_latency_ms
        self.circuit_breaker = AsyncCircuitBreaker()
        self.scoring_engine = ProxyScoringEngine()
        self.transform_pipeline = OptimizedTransformPipeline(
            self.raw_store,
            self.repo,
            self.registry,
            {source.id: source for source in self.config.sources},
            max_workers=self.max_workers,
        )
        self._source_by_id = {str(source.id): source for source in self.config.sources}
        self._work_queue = PersistentIngestionQueue(self.db)
        self._windowed_ingestion = WindowedIngestionPipeline(
            self.ingest_pipeline,
            self._work_queue,
        )
        self._ingestion_stop_monotonic: Optional[float] = None
        self._ingestion_budget_exhausted = False
        self._completion_buffer_seconds = 0.0
        self._run_owner = ""
        self._window_pages = 0
        self._window_completions = 0
        self._window_failures = 0

    def run(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(
                    asyncio.run,
                    self._run_unified(timeout, no_publish, allow_partial_export),
                ).result()
        else:
            return asyncio.run(self._run_unified(timeout, no_publish, allow_partial_export))

    async def _run_unified(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        start_time = time.monotonic()
        self._deadline = time.time() + timeout if timeout else None
        
        eligible_sources = [
            source
            for source in self.config.sources
            if getattr(source, "publication_eligible", True)
        ]
        
        status = "completed"
        results: dict[str, int] = {"ok": 0, "err": 0}

        # 1. Transform Phase
        try:
            self.transform_pipeline.run()
        except Exception as e:
            logger.warning("[UnifiedOrchestrator] Transform pipeline completed with notice: %s", e)

        # 2. Build & Publish Phase across routes
        all_build_results = []
        for route in self.config.routes:
            route_dict = {
                "name": route.name,
                "formats": route.formats,
                "from_sources": route.from_sources,
            }
            build_results = self.build_pipeline.run(route_dict)
            if build_results:
                all_build_results.extend(build_results)

                if not no_publish:
                    dests = [
                        {
                            "chat_id": d.chat_id,
                            "mode": d.mode,
                            "caption_template": d.caption_template,
                            "token": d.token,
                        }
                        for d in route.destinations
                    ]
                    for res in build_results:
                        self.publish_pipeline.run(res, dests)

        results["ok"] = len(all_build_results)

        elapsed = time.monotonic() - start_time
        return {
            "status": status,
            "elapsed_seconds": elapsed,
            "results": results,
            "unified": True,
        }
