from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from typing import Any, Optional

from .orchestrator import Orchestrator
from .resilience import AsyncCircuitBreaker
from .scoring import ProxyScoringEngine
from .geo_routing import GeoRoutingEngine
from .self_healing import SelfHealingDaemon
from ..formats.streaming import StreamingChunkParser
from ..pipeline.optimized_transform import OptimizedTransformPipeline
from ..pipeline.windowed_ingest import WindowedIngestionPipeline
from ..state.ingestion_queue import PersistentIngestionQueue

logger = logging.getLogger(__name__)


class UnifiedOrchestrator(Orchestrator):
    """Unified orchestration engine with resilience-aware execution."""

    def __init__(self, *args: Any, enable_benchmarking: bool = True, max_proxy_latency_ms: int = 1500, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.enable_benchmarking = enable_benchmarking
        self.max_proxy_latency_ms = max_proxy_latency_ms
        self.circuit_breaker = AsyncCircuitBreaker()
        self.scoring_engine = ProxyScoringEngine()
        self.streaming_parser = StreamingChunkParser()
        self.geo_routing = GeoRoutingEngine()
        self.self_healing = SelfHealingDaemon()
        self.transform_pipeline = OptimizedTransformPipeline(
            self.raw_store, self.repo, self.registry,
            {source.id: source for source in self.config.sources},
            max_workers=self.max_workers,
        )
        self._source_by_id = {str(source.id): source for source in self.config.sources}
        self._work_queue = PersistentIngestionQueue(self.db)
        self._windowed_ingestion = WindowedIngestionPipeline(self.ingest_pipeline, self._work_queue)
        self._deadline: Optional[float] = None

    def run(self, timeout: float | None = None, no_publish: bool = False, allow_partial_export: bool = False) -> dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, self._run_unified(timeout, no_publish, allow_partial_export)).result()
        return asyncio.run(self._run_unified(timeout, no_publish, allow_partial_export))

    async def _run_unified(self, timeout: Optional[float], no_publish: bool, allow_partial_export: bool) -> dict[str, Any]:
        start_time = time.monotonic()
        self._deadline = time.time() + timeout if timeout else None
        results: dict[str, int] = {"ok": 0, "err": 0}
        all_build_results: list[Any] = []

        try:
            await self._windowed_ingestion.run(deadline=self._deadline)
        except Exception:
            logger.exception("[UnifiedOrchestrator] ingestion failed")
            results["err"] += 1
            if not allow_partial_export:
                return {"status": "failed", "results": results, "unified": True}

        try:
            self.transform_pipeline.process_pending()
        except Exception:
            logger.exception("[UnifiedOrchestrator] transform failed")
            results["err"] += 1

        seen_file_cutoff_id = self._get_seen_file_max_id()
        for route in self.config.routes:
            if self._deadline and time.time() >= self._deadline:
                break
            route_dict = {
                "name": route.name,
                "formats": route.formats,
                "from_sources": route.from_sources,
                "min_seen_file_id": seen_file_cutoff_id,
            }
            try:
                build_results = self.build_pipeline.run(route_dict)
            except Exception:
                logger.exception("[UnifiedOrchestrator] build failed route=%s", route.name)
                results["err"] += 1
                continue

            if not build_results:
                continue
            all_build_results.extend(build_results)

            if not no_publish:
                dests = [
                    {"chat_id": d.chat_id, "mode": d.mode, "caption_template": d.caption_template, "token": d.token}
                    for d in route.destinations
                ]
                for artifact in build_results:
                    try:
                        self.publish_pipeline.run(artifact, dests)
                    except Exception:
                        logger.exception("[UnifiedOrchestrator] publish failed route=%s", route.name)
                        results["err"] += 1

        results["ok"] = len(all_build_results)
        return {
            "status": "completed",
            "elapsed_seconds": time.monotonic() - start_time,
            "results": results,
            "unified": True,
        }
