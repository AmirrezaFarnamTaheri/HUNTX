from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Optional

from .hardened_orchestrator import HardenedOrchestrator
from ..pipeline.optimized_transform import OptimizedTransformPipeline
from ..pipeline.windowed_ingest import WindowedIngestionPipeline
from ..state.ingestion_queue import PersistentIngestionQueue

logger = logging.getLogger(__name__)


class OptimizedHardenedOrchestrator(HardenedOrchestrator):
    """Hardened runner with persistent newest-window-first ingestion."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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

    def _window_seconds(self) -> int:
        raw = os.environ.get("HUNTX_INGEST_WINDOW_SECONDS", "3600")
        try:
            return max(300, min(int(raw), 24 * 3600))
        except ValueError:
            logger.warning("Invalid HUNTX_INGEST_WINDOW_SECONDS=%r; using 3600", raw)
            return 3600

    def _window_page_size(self) -> int:
        raw = os.environ.get("HUNTX_INGEST_PAGE_SIZE", "100")
        try:
            return max(10, min(int(raw), 1000))
        except ValueError:
            logger.warning("Invalid HUNTX_INGEST_PAGE_SIZE=%r; using 100", raw)
            return 100

    def _lookback_seconds(self) -> int:
        raw = os.environ.get("HUNTX_LIFO_LOOKBACK_HOURS", "").strip()
        if raw:
            try:
                hours = float(raw)
            except ValueError:
                logger.warning("Invalid HUNTX_LIFO_LOOKBACK_HOURS=%r", raw)
            else:
                return max(3600, min(int(hours * 3600), 30 * 24 * 3600))
        configured = float(self.fetch_windows.get("file_fresh_hours", 48) or 48)
        return max(3600, min(int(configured * 3600), 30 * 24 * 3600))

    def _remaining_ingestion_budget(self) -> Optional[float]:
        stop = self._ingestion_stop_monotonic
        if stop is None:
            return None
        return stop - time.monotonic()

    async def _run_direct_source(
        self,
        source: Any,
        results: dict[str, int],
        lock: asyncio.Lock,
        configured_timeout: float,
    ) -> None:
        remaining = self._remaining_ingestion_budget()
        if remaining is not None and remaining <= 0:
            self._ingestion_budget_exhausted = True
            return
        timeout = configured_timeout if remaining is None else min(configured_timeout, remaining)
        success = False
        try:
            success = bool(
                await asyncio.wait_for(
                    self._ingest_one_source_async(source),
                    timeout=timeout,
                )
            )
        except asyncio.TimeoutError:
            if remaining is not None and timeout < configured_timeout:
                self._ingestion_budget_exhausted = True
                logger.warning(
                    "[Worker] Ingestion budget reached while processing %s; continuing downstream",
                    source.id,
                )
            else:
                logger.error("[Worker] Source %s exceeded %.1fs and was isolated", source.id, timeout)
        except Exception:
            logger.exception("[Worker] Source %s failed", source.id)
        finally:
            async with lock:
                results["ok" if success else "err"] += 1

    async def _run_persistent_windows(
        self,
        results: dict[str, int],
        lock: asyncio.Lock,
        configured_timeout: float,
    ) -> None:
        page_size = self._window_page_size()
        lease_seconds = int(configured_timeout) + 60

        while True:
            remaining = self._remaining_ingestion_budget()
            if remaining is not None and remaining <= 0:
                self._ingestion_budget_exhausted = True
                return

            item = self._work_queue.claim_next(
                self._run_owner,
                lease_seconds=lease_seconds,
            )
            if item is None:
                return

            source = self._source_by_id.get(item.source_id)
            if source is None or getattr(source, "telegram_user", None) is None:
                self._window_failures += 1
                self._work_queue.fail(
                    item.id,
                    self._run_owner,
                    f"source configuration {item.source_id!r} is unavailable",
                    retry_delay=3600,
                )
                async with lock:
                    results["err"] += 1
                continue

            timeout = configured_timeout if remaining is None else min(configured_timeout, remaining)
            wall_deadline = time.time() + timeout
            try:
                page_result = await asyncio.wait_for(
                    self._windowed_ingestion.run_page(
                        source,
                        item,
                        owner=self._run_owner,
                        deadline=wall_deadline,
                        page_size=page_size,
                    ),
                    timeout=timeout,
                )
                self._window_pages += 1
                if bool(page_result["completed"]):
                    self._window_completions += 1
                    async with lock:
                        results["ok"] += 1
                logger.info(
                    "[LIFO] source=%s window=[%s,%s) scanned=%s ingested=%s "
                    "cursor=%s completed=%s",
                    item.source_id,
                    item.window_start_ts,
                    item.window_end_ts,
                    page_result["scanned_messages"],
                    page_result["items_ingested"],
                    page_result["continuation_cursor"],
                    page_result["completed"],
                )
            except asyncio.TimeoutError:
                self._window_failures += 1
                retry_delay = 1 if remaining is not None and timeout < configured_timeout else 60
                self._work_queue.fail(
                    item.id,
                    self._run_owner,
                    "window page timed out",
                    retry_delay=retry_delay,
                )
                if remaining is not None and timeout < configured_timeout:
                    self._ingestion_budget_exhausted = True
                    return
                async with lock:
                    results["err"] += 1
            except Exception as exc:
                self._window_failures += 1
                retry_delay = min(3600, 2 ** min(item.attempt_count, 10))
                self._work_queue.fail(
                    item.id,
                    self._run_owner,
                    str(exc),
                    retry_delay=retry_delay,
                )
                async with lock:
                    results["err"] += 1
                logger.exception(
                    "[LIFO] Window failed source=%s window=[%s,%s)",
                    item.source_id,
                    item.window_start_ts,
                    item.window_end_ts,
                )

    async def _worker_async(
        self,
        source_queue: asyncio.Queue[Any],
        results: dict[str, int],
        lock: asyncio.Lock,
    ) -> None:
        configured_timeout = self._source_timeout()

        while True:
            try:
                source = source_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if getattr(source, "type", None) != "telegram_user":
                    await self._run_direct_source(source, results, lock, configured_timeout)
            finally:
                source_queue.task_done()

        await self._run_persistent_windows(results, lock, configured_timeout)

    async def _run_hardened(
        self,
        timeout: Optional[float],
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        original = list(self.config.sources)
        self._source_by_id = {str(source.id): source for source in original}
        self._ingestion_budget_exhausted = False
        self._window_pages = 0
        self._window_completions = 0
        self._window_failures = 0
        self._run_owner = uuid.uuid4().hex
        self._completion_buffer_seconds = self._completion_buffer(timeout)

        if timeout is not None:
            ingestion_budget = max(0.0, timeout - self._completion_buffer_seconds)
            self._ingestion_stop_monotonic = time.monotonic() + ingestion_budget
        else:
            ingestion_budget = None
            self._ingestion_stop_monotonic = None

        recovered = self._work_queue.recover_expired_leases()
        seed = self._work_queue.seed_rolling_horizon(
            original,
            lookback_seconds=self._lookback_seconds(),
            window_seconds=self._window_seconds(),
        )
        logger.info(
            "[Orchestrator] budgets total=%s ingestion=%s completion_buffer=%s "
            "lifo_campaign=%s seeded=%s recovered_leases=%s",
            timeout,
            ingestion_budget,
            self._completion_buffer_seconds,
            seed["campaign_id"],
            seed["inserted"],
            recovered,
        )

        try:
            summary = await super()._run_hardened(
                timeout,
                no_publish,
                allow_partial_export,
            )
        finally:
            released = self._work_queue.release_owner(self._run_owner)
            if released:
                logger.warning("[LIFO] Released %s unfinished lease(s) to residue", released)
            self.config.sources = original
            self._ingestion_stop_monotonic = None

        residue = self._work_queue.summary()
        summary["completion_buffer_seconds"] = self._completion_buffer_seconds
        summary["ingestion_budget_seconds"] = ingestion_budget
        summary["ingestion_budget_exhausted"] = self._ingestion_budget_exhausted
        summary["lifo_campaign_id"] = seed["campaign_id"]
        summary["lifo_anchor_ts"] = seed["anchor_ts"]
        summary["lifo_target_start_ts"] = seed["target_start_ts"]
        summary["lifo_windows_seeded"] = seed["inserted"]
        summary["lifo_pages_processed"] = self._window_pages
        summary["lifo_windows_completed"] = self._window_completions
        summary["lifo_window_failures"] = self._window_failures
        summary["lifo_residue"] = residue
        summary["ingest_skipped_due_to_budget"] = int(residue.get("remaining", 0))

        if self._ingestion_budget_exhausted and summary.get("status") == "completed":
            summary["status"] = "partial"
        if self._ingestion_budget_exhausted:
            summary["partial_reason"] = "ingestion_budget_exhausted"
        elif int(residue.get("remaining", 0)) > 0 and summary.get("status") == "completed":
            summary["status"] = "partial"
            summary["partial_reason"] = "ingestion_residue_remaining"

        logger.info("[Orchestrator] optimized final summary=%s", summary)
        return summary
