from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

from .latency_benchmarker import filter_proxies_by_latency
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .resilience import AsyncCircuitBreaker, CircuitBreakerOpenError
from .scoring import ProxyScoringEngine

logger = logging.getLogger(__name__)


class UnifiedOrchestrator(OptimizedHardenedOrchestrator):
    """Consolidated resilient orchestrator using persistent windowed ingestion."""

    def __init__(
        self,
        *args: Any,
        enable_benchmarking: bool = True,
        max_proxy_latency_ms: int = 1500,
        min_proxy_quality_score: float = 25.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if max_proxy_latency_ms < 0:
            raise ValueError("max_proxy_latency_ms must be non-negative")
        if not 0.0 <= min_proxy_quality_score <= 100.0:
            raise ValueError("min_proxy_quality_score must be between 0 and 100")

        self.enable_benchmarking = enable_benchmarking
        self.max_proxy_latency_ms = max_proxy_latency_ms
        self.min_proxy_quality_score = min_proxy_quality_score
        self.circuit_breaker = AsyncCircuitBreaker()
        self.scoring_engine = ProxyScoringEngine()
        self._deadline: Optional[float] = None

    def run(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        """Run from synchronous code; async callers must await :meth:`run_async`."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(timeout, no_publish, allow_partial_export))
        raise RuntimeError("UnifiedOrchestrator.run() cannot block an active event loop; use await run_async()")

    async def run_async(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        """Run the unified pipeline without blocking an active event loop."""
        return await self._run_unified(timeout, no_publish, allow_partial_export)

    async def _run_ingestion(
        self,
        sources: list[Any],
        results: dict[str, int],
        timeout: Optional[float],
    ) -> None:
        """Run direct and persistent-window ingestion using inherited workers."""
        self._source_by_id = {str(source.id): source for source in sources}
        self._run_owner = uuid.uuid4().hex
        self._ingestion_budget_exhausted = False
        self._window_pages = 0
        self._window_completions = 0
        self._window_failures = 0
        self._completion_buffer_seconds = 0.0
        self._ingestion_stop_monotonic = time.monotonic() + timeout if timeout is not None else None

        self._work_queue.recover_expired_leases()
        self._work_queue.seed_rolling_horizon(
            sources,
            lookback_seconds=self._lookback_seconds(),
            window_seconds=self._window_seconds(),
        )

        source_queue: asyncio.Queue[Any] = asyncio.Queue()
        for source in sources:
            await source_queue.put(source)
        lock = asyncio.Lock()
        worker_count = max(1, min(self.max_workers, len(sources) or 1))
        tasks = [asyncio.create_task(self._worker_async(source_queue, results, lock)) for _ in range(worker_count)]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            released = self._work_queue.release_owner(self._run_owner)
            if released:
                logger.warning("[UnifiedOrchestrator] released %s unfinished ingestion lease(s)", released)
            await self._windowed_ingestion.close()
            self._ingestion_stop_monotonic = None

    @staticmethod
    def _proxy_line(record: dict[str, Any]) -> str:
        data = record.get("data")
        if not isinstance(data, dict):
            return ""
        for key in ("line", "uri", "raw_uri", "raw"):
            value = data.get(key)
            if isinstance(value, str) and "://" in value:
                return value
        return ""

    async def _prepare_route_records(
        self,
        route: Any,
        min_seen_file_id: int,
        results: dict[str, int],
    ) -> list[dict[str, Any]]:
        records = self.repo.get_records_for_build(
            route.formats,
            route.from_sources,
            min_seen_file_id=min_seen_file_id,
        )
        if not self.enable_benchmarking:
            return records

        proxy_records: list[dict[str, Any]] = []
        passthrough_records: list[dict[str, Any]] = []
        for record in records:
            if self._proxy_line(record):
                proxy_records.append(record)
            else:
                passthrough_records.append(record)

        benchmarked = proxy_records
        if proxy_records:
            try:
                benchmarked = await self.circuit_breaker.call(
                    filter_proxies_by_latency,
                    proxy_records,
                    max_latency_ms=float(self.max_proxy_latency_ms),
                    concurrency=min(50, max(1, len(proxy_records))),
                    timeout=min(3.0, max(0.1, self.max_proxy_latency_ms / 1000.0)),
                    retries=1,
                    retry_backoff=0.1,
                )
            except CircuitBreakerOpenError:
                logger.warning("[UnifiedOrchestrator] latency benchmark circuit is open")
                results["err"] += len(proxy_records)
                benchmarked = []
            except Exception:
                logger.exception("[UnifiedOrchestrator] latency benchmark failed")
                results["err"] += 1
                benchmarked = []

        accepted: list[dict[str, Any]] = []
        for record in benchmarked:
            prepared = dict(record)
            data = prepared.get("data")
            if not isinstance(data, dict):
                continue
            prepared_data = dict(data)
            score = self.scoring_engine.score_proxy(prepared_data)
            prepared_data["quality_score"] = score
            prepared["data"] = prepared_data
            if score >= self.min_proxy_quality_score:
                accepted.append(prepared)
            else:
                logger.info("[UnifiedOrchestrator] excluded low-quality proxy score=%.2f", score)

        return passthrough_records + accepted

    async def _run_unified(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        deadline_monotonic = started_at + timeout if timeout is not None else None
        self._deadline = time.time() + timeout if timeout is not None else None
        results: dict[str, int] = {"ok": 0, "err": 0}
        all_build_results: list[Any] = []

        original_sources = list(self.config.sources)
        eligible_sources = [
            source for source in original_sources if bool(getattr(source, "publication_eligible", True))
        ]
        ingestion_sources = await self._canonical_ingestion_sources(eligible_sources)
        self.config.sources = ingestion_sources
        try:
            await self._run_ingestion(ingestion_sources, results, timeout)
        except Exception:
            logger.exception("[UnifiedOrchestrator] ingestion failed")
            results["err"] += 1
            if not allow_partial_export:
                return {
                    "status": "failed",
                    "elapsed_seconds": time.monotonic() - started_at,
                    "results": results,
                    "unified": True,
                }
        finally:
            self.config.sources = original_sources

        try:
            transform_summary = self.transform_pipeline.process_pending(deadline=deadline_monotonic)
            if transform_summary.get("failed"):
                results["err"] += int(transform_summary["failed"])
        except Exception:
            logger.exception("[UnifiedOrchestrator] transform failed")
            results["err"] += 1
            if not allow_partial_export:
                return {
                    "status": "failed",
                    "elapsed_seconds": time.monotonic() - started_at,
                    "results": results,
                    "unified": True,
                }

        seen_file_cutoff_id = self._get_seen_file_max_id()
        for route in self.config.routes:
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                results["err"] += 1
                break

            route_dict = {
                "name": route.name,
                "formats": route.formats,
                "from_sources": route.from_sources,
                "min_seen_file_id": seen_file_cutoff_id,
            }
            try:
                records = await self._prepare_route_records(route, seen_file_cutoff_id, results)
                build_results = self.build_pipeline.run(route_dict, records=records)
            except Exception:
                logger.exception("[UnifiedOrchestrator] build failed route=%s", route.name)
                results["err"] += 1
                continue

            if not build_results:
                continue
            all_build_results.extend(build_results)

            if no_publish:
                continue
            destinations = [
                {
                    "chat_id": destination.chat_id,
                    "mode": destination.mode,
                    "caption_template": destination.caption_template,
                    "token": destination.token,
                }
                for destination in route.destinations
            ]
            for artifact in build_results:
                try:
                    self.publish_pipeline.run(artifact, destinations)
                except Exception:
                    logger.exception("[UnifiedOrchestrator] publish failed route=%s", route.name)
                    results["err"] += 1

        results["ok"] += len(all_build_results)
        return {
            "status": "completed" if results["err"] == 0 else "completed_with_errors",
            "elapsed_seconds": time.monotonic() - started_at,
            "results": results,
            "unified": True,
        }
