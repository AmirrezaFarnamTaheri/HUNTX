import asyncio
import concurrent.futures
import logging
import time
from typing import Any, Optional

from ..connectors.base import run_sync
from .deadline import Deadline, DeadlineExceeded
from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def _classify_completed_status(
    *,
    ingest_ok: int,
    ingest_err: int,
    failed_routes: int,
    publish_failures: int,
) -> str:
    """Classify a run that reached the end of every bounded stage.

    HUNTX aggregates independently volatile external sources. Source failures
    are degraded input coverage only when successful ingestions are a strict
    majority and every build/publish route succeeds. Route or publication
    failures remain partial, while zero successful ingestions are a hard
    failure.
    """

    if failed_routes or publish_failures:
        return "partial"
    if ingest_ok <= 0:
        return "failed"
    if ingest_err >= ingest_ok:
        return "partial"
    return "completed"


class HardenedOrchestrator(Orchestrator):
    """Run control with bounded stage concurrency and explicit outcomes."""

    def run(  # type: ignore[override]
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        """Execute the deadline-aware pipeline in a sync or async caller."""
        return run_sync(self._run_hardened(timeout, no_publish, allow_partial_export))

    async def _run_hardened(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        start_time = time.monotonic()
        deadline = Deadline(timeout)
        self._deadline = time.time() + timeout if timeout else None
        eligible_sources = [
            source
            for source in self.config.sources
            if getattr(source, "publication_eligible", True)
        ]
        eligible_source_ids = {str(source.id) for source in eligible_sources}
        excluded_sources = len(self.config.sources) - len(eligible_sources)
        total_sources = len(eligible_sources)
        total_routes = len(self.config.routes)
        ingestion_workers = min(self.max_workers, total_sources) if total_sources else 0
        build_workers = min(self.max_workers, total_routes) if total_routes else 0
        publish_workers = max(1, self.max_workers)
        seen_file_cutoff_id = self._get_seen_file_max_id()

        status = "completed"
        timed_out_stage: Optional[str] = None
        results: dict[str, int] = {"ok": 0, "err": 0}
        failed_routes: set[str] = set()
        total_artifacts = 0
        publish_attempts = 0
        publish_failures = 0
        ingestion_cancelled = 0
        build_pending = 0
        build_cancelled = 0
        publish_pending = 0
        publish_cancelled = 0
        all_build_results: list[Any] = []
        stage_seconds: dict[str, float] = {}
        transform_completed = True
        transform_stop_reason = "complete"

        def remaining() -> Optional[float]:
            return deadline.remaining_seconds()

        def mark_timeout(stage: str) -> None:
            nonlocal status, timed_out_stage
            status = "timed_out"
            timed_out_stage = stage
            logger.error("[Orchestrator] Deadline exhausted during %s", stage)

        def route_payload(route: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            approved_route_sources = [
                source_id
                for source_id in route.from_sources
                if str(source_id) in eligible_source_ids
            ]
            excluded_route_sources = len(route.from_sources) - len(approved_route_sources)
            if excluded_route_sources:
                logger.warning(
                    "[Orchestrator] route=%s excluded %s non-approved source(s) from build",
                    route.name,
                    excluded_route_sources,
                )
            route_dict = {
                "name": route.name,
                "formats": route.formats,
                "from_sources": approved_route_sources,
                "min_seen_file_id": seen_file_cutoff_id,
            }
            destinations = [
                {
                    "chat_id": destination.chat_id,
                    "mode": destination.mode,
                    "caption_template": destination.caption_template,
                    "token": destination.token,
                    "required": getattr(destination, "required", True),
                }
                for destination in route.destinations
            ]
            return route_dict, destinations

        logger.info(
            "[Orchestrator] start approved_sources=%s excluded_sources=%s routes=%s "
            "ingestion_workers=%s build_workers=%s publish_workers=%s timeout=%s",
            total_sources,
            excluded_sources,
            total_routes,
            ingestion_workers,
            build_workers,
            publish_workers,
            timeout,
        )

        if not eligible_sources:
            return {
                "status": "failed",
                "timed_out": False,
                "timed_out_stage": None,
                "duration_seconds": time.monotonic() - start_time,
                "stage_seconds": stage_seconds,
                "partial_export_enabled": allow_partial_export,
                "total_artifacts": 0,
                "publish_attempts": 0,
                "publish_failures": 0,
                "publish_pending": 0,
                "publish_cancelled": 0,
                "ingest_ok": 0,
                "ingest_err": 0,
                "degraded_source_failures": 0,
                "ingestion_cancelled": 0,
                "build_pending": 0,
                "build_cancelled": 0,
                "failed_routes": 0,
                "approved_sources": 0,
                "excluded_sources": excluded_sources,
                "transform_completed": False,
                "transform_stop_reason": "not_started",
                "reason": "no_approved_sources",
            }

        ingestion_start = time.monotonic()
        source_queue: asyncio.Queue[Any] = asyncio.Queue()
        for source in eligible_sources:
            await source_queue.put(source)
        result_lock = asyncio.Lock()
        ingestion_tasks = [
            asyncio.create_task(self._worker_async(source_queue, results, result_lock))
            for _ in range(ingestion_workers)
        ]
        try:
            left = remaining()
            if left is not None and left <= 0:
                raise asyncio.TimeoutError
            gather = asyncio.gather(*ingestion_tasks)
            await asyncio.wait_for(gather, timeout=left) if left is not None else await gather
        except asyncio.TimeoutError:
            mark_timeout("ingestion")
            for task in ingestion_tasks:
                if task.cancel():
                    ingestion_cancelled += 1
            await asyncio.gather(*ingestion_tasks, return_exceptions=True)
        except Exception:
            status = "failed"
            logger.exception("[Orchestrator] Ingestion failed")
            for task in ingestion_tasks:
                task.cancel()
            await asyncio.gather(*ingestion_tasks, return_exceptions=True)
        finally:
            stage_seconds["ingestion"] = time.monotonic() - ingestion_start

        if status == "completed":
            transform_start = time.monotonic()
            transform_deadline = start_time + timeout if timeout is not None else None
            try:
                transform_summary = self.transform_pipeline.process_pending(
                    deadline_monotonic=transform_deadline
                )
                if isinstance(transform_summary, dict):
                    transform_completed = bool(transform_summary.get("completed", True))
                    transform_stop_reason = str(
                        transform_summary.get("stop_reason", "complete")
                    )
                    if not transform_completed:
                        if transform_stop_reason == "deadline":
                            mark_timeout("transformation")
                        else:
                            status = "partial"
                            logger.error(
                                "[Orchestrator] Transformation did not fully drain: %s",
                                transform_stop_reason,
                            )
            except Exception:
                status = "failed"
                transform_completed = False
                transform_stop_reason = "exception"
                logger.exception("[Orchestrator] Transformation failed")
            finally:
                stage_seconds["transformation"] = time.monotonic() - transform_start
            time_left = remaining()
            if status == "completed" and time_left is not None and time_left <= 0:
                mark_timeout("transformation")
                transform_completed = False
                transform_stop_reason = "deadline"

        route_destinations: dict[str, list[dict[str, Any]]] = {}
        if status == "completed" and total_routes:
            build_start = time.monotonic()
            build_executor = concurrent.futures.ThreadPoolExecutor(max_workers=build_workers)
            build_futures: dict[concurrent.futures.Future[Any], str] = {}
            try:
                for route in self.config.routes:
                    route_dict, destinations = route_payload(route)
                    route_destinations[route.name] = destinations
                    build_future = build_executor.submit(self.build_pipeline.run, route_dict, deadline=deadline)
                    build_futures[build_future] = route.name

                left = remaining()
                if left is not None and left <= 0:
                    mark_timeout("build")
                    done: set[concurrent.futures.Future[Any]] = set()
                    not_done = set(build_futures)
                else:
                    done, not_done = concurrent.futures.wait(build_futures, timeout=left)

                for completed_build in done:
                    route_name = build_futures[completed_build]
                    try:
                        build_results = completed_build.result() or []
                        total_artifacts += len(build_results)
                        all_build_results.extend(build_results)
                    except DeadlineExceeded:
                        failed_routes.add(route_name)
                        mark_timeout("build")
                    except Exception:
                        failed_routes.add(route_name)
                        if status == "completed":
                            status = "partial"
                        logger.exception("[Orchestrator] Route build failed: %s", route_name)

                if not_done:
                    mark_timeout("build")
                    build_pending = len(not_done)
                    for pending_build in not_done:
                        if pending_build.cancel():
                            build_cancelled += 1
            finally:
                build_executor.shutdown(wait=True, cancel_futures=True)
                stage_seconds["build"] = time.monotonic() - build_start

        pending_publish: dict[concurrent.futures.Future[Any], str] = {}
        if status == "completed" and not no_publish and all_build_results:
            publish_start = time.monotonic()
            publisher = concurrent.futures.ThreadPoolExecutor(max_workers=publish_workers)
            try:
                for build_result in all_build_results:
                    if not isinstance(build_result, dict):
                        logger.warning(
                            "[Orchestrator] Skipping non-dict build result: %r",
                            build_result,
                        )
                        continue
                    route_name_val = build_result.get("route_name")
                    artifact_hash_val = build_result.get("artifact_hash")
                    if (
                        not isinstance(route_name_val, str)
                        or not route_name_val
                        or not artifact_hash_val
                    ):
                        logger.warning(
                            "[Orchestrator] Skipping build result missing "
                            "route_name/artifact_hash: %r",
                            build_result,
                        )
                        continue
                    route_name = route_name_val
                    publish_future = publisher.submit(
                        self.publish_pipeline.run,
                        build_result,
                        route_destinations.get(route_name, []),
                        deadline=deadline,
                    )
                    pending_publish[publish_future] = route_name

                left = remaining()
                if left is not None and left <= 0:
                    mark_timeout("publishing")
                    done = set()
                    not_done = set(pending_publish)
                else:
                    done, not_done = concurrent.futures.wait(
                        pending_publish,
                        timeout=left,
                    )
                publish_attempts = len(done)
                for completed_publish in done:
                    route_name = pending_publish[completed_publish]
                    try:
                        completed_publish.result()
                    except DeadlineExceeded:
                        failed_routes.add(route_name)
                        mark_timeout("publishing")
                    except Exception:
                        publish_failures += 1
                        failed_routes.add(route_name)
                        if status == "completed":
                            status = "partial"
                        logger.exception(
                            "[Orchestrator] Publish failed for route %s",
                            route_name,
                        )
                if not_done:
                    mark_timeout("publishing")
                    publish_pending = len(not_done)
                    for pending_item in not_done:
                        if pending_item.cancel():
                            publish_cancelled += 1
            finally:
                publisher.shutdown(wait=True, cancel_futures=True)
                stage_seconds["publishing"] = time.monotonic() - publish_start

        if status == "completed":
            status = _classify_completed_status(
                ingest_ok=results["ok"],
                ingest_err=results["err"],
                failed_routes=len(failed_routes),
                publish_failures=publish_failures,
            )
            if status == "completed" and results["err"]:
                logger.warning(
                    "[Orchestrator] Completed with %s isolated source failure(s); "
                    "%s source(s) completed and all release routes succeeded",
                    results["err"],
                    results["ok"],
                )

        should_export = status == "completed" or (
            status == "timed_out" and allow_partial_export
        )
        export_start = time.monotonic()
        if should_export:
            try:
                self._export_outputs(all_build_results)
                self._export_dev_outputs(all_build_results)
            except Exception:
                status = "failed"
                logger.exception("[Orchestrator] Output export failed")
        elif all_build_results:
            logger.warning(
                "[Orchestrator] Partial artifacts were not exported because "
                "partial export is disabled"
            )
        stage_seconds["export"] = time.monotonic() - export_start

        cleanup_skipped_due_to_deadline = deadline.expired()
        if cleanup_skipped_due_to_deadline:
            logger.warning("[Orchestrator] Skipping cleanup because the global deadline is exhausted")
            stage_seconds["cleanup"] = 0.0
        else:
            cleanup_start = time.monotonic()
            try:
                self.raw_store.prune_processed(self.repo)
                self.raw_store.prune_orphans(self.repo)
                self.artifact_store.prune_archive()
            except Exception:
                if status == "completed":
                    status = "partial"
                logger.exception("[Orchestrator] Cleanup failed")
            finally:
                stage_seconds["cleanup"] = time.monotonic() - cleanup_start

        duration = time.monotonic() - start_time
        summary = {
            "status": status,
            "timed_out": status == "timed_out",
            "timed_out_stage": timed_out_stage,
            "duration_seconds": duration,
            "stage_seconds": {
                key: round(value, 3) for key, value in stage_seconds.items()
            },
            "partial_export_enabled": allow_partial_export,
            "total_artifacts": total_artifacts,
            "publish_attempts": publish_attempts,
            "publish_failures": publish_failures,
            "publish_pending": publish_pending,
            "publish_cancelled": publish_cancelled,
            "ingest_ok": results["ok"],
            "ingest_err": results["err"],
            "degraded_source_failures": results["err"] if results["ok"] else 0,
            "ingestion_cancelled": ingestion_cancelled,
            "build_pending": build_pending,
            "build_cancelled": build_cancelled,
            "failed_routes": len(failed_routes),
            "approved_sources": total_sources,
            "excluded_sources": excluded_sources,
            "ingestion_workers": ingestion_workers,
            "build_workers": build_workers,
            "publish_workers": publish_workers,
            "transform_completed": transform_completed,
            "transform_stop_reason": transform_stop_reason,
            "cleanup_skipped_due_to_deadline": cleanup_skipped_due_to_deadline,
        }
        logger.info("[Orchestrator] Final run summary: %s", summary)
        return summary
