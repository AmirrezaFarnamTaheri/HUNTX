import asyncio
import concurrent.futures
import logging
import time
from typing import Any, Optional

from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class HardenedOrchestrator(Orchestrator):
    """Run-control replacement with explicit outcomes and bounded publish waits."""

    def run(  # type: ignore[override]
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    asyncio.run,
                    self._run_hardened(timeout, no_publish, allow_partial_export),
                )
                return future.result()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        return loop.run_until_complete(
            self._run_hardened(timeout, no_publish, allow_partial_export)
        )

    async def _run_hardened(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        start_time = time.monotonic()
        self._deadline = time.time() + timeout if timeout else None
        total_sources = len(self.config.sources)
        total_routes = len(self.config.routes)
        effective_workers = min(self.max_workers, total_sources)
        seen_file_cutoff_id = self._get_seen_file_max_id()

        status = "completed"
        timed_out_stage: Optional[str] = None
        results = {"ok": 0, "err": 0}
        failed_routes: set[str] = set()
        total_artifacts = 0
        publish_attempts = 0
        publish_failures = 0
        all_build_results: list[Any] = []

        def remaining() -> Optional[float]:
            if timeout is None:
                return None
            return max(0.0, timeout - (time.monotonic() - start_time))

        def mark_timeout(stage: str) -> None:
            nonlocal status, timed_out_stage
            status = "timed_out"
            timed_out_stage = stage
            logger.error("[Orchestrator] Deadline exhausted during %s", stage)

        logger.info(
            "[Orchestrator] hardened run start sources=%s routes=%s workers=%s timeout=%s",
            total_sources,
            total_routes,
            effective_workers,
            timeout,
        )

        source_queue: asyncio.Queue[Any] = asyncio.Queue()
        for source in self.config.sources:
            await source_queue.put(source)
        result_lock = asyncio.Lock()
        ingestion_tasks = [
            asyncio.create_task(self._worker_async(source_queue, results, result_lock))
            for _ in range(effective_workers)
        ]
        try:
            left = remaining()
            if left is not None and left <= 0:
                raise asyncio.TimeoutError
            if left is not None:
                await asyncio.wait_for(asyncio.gather(*ingestion_tasks), timeout=left)
            else:
                await asyncio.gather(*ingestion_tasks)
        except asyncio.TimeoutError:
            mark_timeout("ingestion")
            for task in ingestion_tasks:
                task.cancel()
            await asyncio.gather(*ingestion_tasks, return_exceptions=True)
        except Exception:
            status = "failed"
            logger.exception("[Orchestrator] Ingestion failed")
            for task in ingestion_tasks:
                task.cancel()
            await asyncio.gather(*ingestion_tasks, return_exceptions=True)

        if status == "completed":
            try:
                self.transform_pipeline.process_pending()
            except Exception:
                status = "failed"
                logger.exception("[Orchestrator] Transformation failed")
            time_left = remaining()
            if time_left is not None and time_left <= 0:
                mark_timeout("transformation")

        publisher: Optional[concurrent.futures.ThreadPoolExecutor] = None
        pending_publish: dict[concurrent.futures.Future[Any], str] = {}
        if status == "completed":
            publisher = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
            try:
                for route in self.config.routes:
                    time_left = remaining()
                    if time_left is not None and time_left <= 0:
                        mark_timeout("build")
                        break
                    try:
                        route_dict = {
                            "name": route.name,
                            "formats": route.formats,
                            "from_sources": route.from_sources,
                            "min_seen_file_id": seen_file_cutoff_id,
                        }
                        build_results = self.build_pipeline.run(route_dict)
                        total_artifacts += len(build_results or [])
                        all_build_results.extend(build_results or [])
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
                        for build_result in build_results or []:
                            future = publisher.submit(
                                self.publish_pipeline.run,
                                build_result,
                                destinations,
                            )
                            pending_publish[future] = route.name
                    except Exception:
                        failed_routes.add(route.name)
                        logger.exception("[Orchestrator] Route build failed: %s", route.name)

                if status == "completed" and pending_publish:
                    left = remaining()
                    if left is not None and left <= 0:
                        mark_timeout("publishing")
                    else:
                        done, not_done = concurrent.futures.wait(
                            pending_publish,
                            timeout=left,
                        )
                        for future in done:
                            publish_attempts += 1
                            route_name = pending_publish[future]
                            try:
                                future.result()
                            except Exception:
                                publish_failures += 1
                                failed_routes.add(route_name)
                                logger.exception(
                                    "[Orchestrator] Publish failed for route %s",
                                    route_name,
                                )
                        if not_done:
                            mark_timeout("publishing")
                            for future in not_done:
                                future.cancel()
            finally:
                publisher.shutdown(wait=False, cancel_futures=True)

        should_export = status == "completed" or (
            status == "timed_out" and allow_partial_export
        )
        if should_export:
            try:
                self._export_outputs(all_build_results)
                self._export_dev_outputs(all_build_results)
            except Exception:
                status = "failed"
                logger.exception("[Orchestrator] Output export failed")
        elif all_build_results:
            logger.warning(
                "[Orchestrator] Partial artifacts were not exported because partial export is disabled"
            )

        try:
            self.raw_store.prune_processed(self.repo)
            self.raw_store.prune_orphans(self.repo)
            self.artifact_store.prune_archive()
        except Exception:
            if status == "completed":
                status = "partial"
            logger.exception("[Orchestrator] Cleanup failed")

        if status == "completed" and (results["err"] or failed_routes or publish_failures):
            status = "partial"

        duration = time.monotonic() - start_time
        summary = {
            "status": status,
            "timed_out": status == "timed_out",
            "timed_out_stage": timed_out_stage,
            "duration_seconds": duration,
            "partial_export_enabled": allow_partial_export,
            "total_artifacts": total_artifacts,
            "publish_attempts": publish_attempts,
            "publish_failures": publish_failures,
            "ingest_ok": results["ok"],
            "ingest_err": results["err"],
            "failed_routes": len(failed_routes),
        }
        logger.info("[Orchestrator] Final run summary: %s", summary)
        return summary
