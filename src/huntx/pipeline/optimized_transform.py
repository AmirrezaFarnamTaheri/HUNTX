from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from collections import Counter
from typing import Any, Optional

from .transform import (
    TRANSFORM_BATCH_SIZE,
    _DEFAULT_MAX_BATCHES,
    _DEFAULT_MAX_RECORDS,
    _positive_limit,
    TransformPipeline,
)

logger = logging.getLogger(__name__)


class OptimizedTransformPipeline(TransformPipeline):
    """Adaptive transform loop with the same bounded contract as the base pipeline."""

    def _effective_batch_size(self) -> int:
        raw = os.environ.get("HUNTX_TRANSFORM_BATCH_SIZE", "").strip()
        if raw:
            try:
                return max(1, min(int(raw), 2000))
            except ValueError:
                logger.warning("Invalid HUNTX_TRANSFORM_BATCH_SIZE=%r", raw)
        return max(TRANSFORM_BATCH_SIZE, min(1000, max(1, self.max_workers) * 64))

    def process_pending(
        self,
        *,
        deadline_monotonic: Optional[float] = None,
        max_batches: Optional[int] = None,
        max_records: Optional[int] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        batch_size = self._effective_batch_size()
        batch_limit = _positive_limit(
            "HUNTX_TRANSFORM_MAX_BATCHES",
            max_batches,
            _DEFAULT_MAX_BATCHES,
            100_000,
        )
        record_limit = _positive_limit(
            "HUNTX_TRANSFORM_MAX_RECORDS",
            max_records,
            _DEFAULT_MAX_RECORDS,
            100_000_000,
        )
        totals = {"processed": 0, "failed": 0, "skipped": 0, "records": 0}
        formats: Counter[str] = Counter()
        batches = 0
        deferred = 0
        stop_reason = "complete"

        logger.info(
            "[Transform] optimized start workers=%s batch_size=%s max_batches=%s max_records=%s",
            self.max_workers,
            batch_size,
            batch_limit,
            record_limit,
        )
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, self.max_workers))
        try:
            while True:
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                    stop_reason = "deadline"
                    break
                if batches >= batch_limit:
                    stop_reason = "max_batches"
                    break
                if totals["records"] >= record_limit:
                    stop_reason = "max_records"
                    break

                batch = self.state_repo.get_pending_files(limit=batch_size)
                if not batch:
                    break
                batches += 1

                futures = {executor.submit(self._process_single_file, row): row for row in batch}
                timeout = None
                if deadline_monotonic is not None:
                    timeout = max(0.0, deadline_monotonic - time.monotonic())
                done, not_done = concurrent.futures.wait(futures, timeout=timeout)
                if not_done:
                    for future in not_done:
                        future.cancel()
                    stop_reason = "deadline"

                results: list[dict[str, Any]] = []
                for future in done:
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error("[Transform] Worker thread failed: %s", exc)
                        continue
                    results.append(result)
                    format_id = result.get("format")
                    if isinstance(format_id, str):
                        formats[format_id] += 1

                remaining_records = record_limit - totals["records"]
                commit_results: list[dict[str, Any]] = []
                selected_records = 0
                for result in results:
                    generated = int(result.get("records", 0)) if result.get("status") == "ok" else 0
                    if generated > remaining_records - selected_records:
                        deferred += 1
                        stop_reason = "max_records"
                        continue
                    commit_results.append(result)
                    selected_records += generated

                records = processed = failed = skipped = 0
                if commit_results:
                    records, processed, failed, skipped = self._flush_batch(commit_results)
                totals["records"] += records
                totals["processed"] += processed
                totals["failed"] += failed
                totals["skipped"] += skipped
                logger.info(
                    "[Transform] optimized batch=%s files=%s committed=%s deferred=%s totals=%s",
                    batches,
                    len(batch),
                    len(commit_results),
                    len(results) - len(commit_results),
                    totals,
                )
                if stop_reason != "complete":
                    break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        summary: dict[str, Any] = {
            "completed": stop_reason == "complete",
            "stop_reason": stop_reason,
            **totals,
            "batches": batches,
            "batch_size": batch_size,
            "deferred": deferred,
            "duration_seconds": time.monotonic() - started,
            "formats": dict(formats),
        }
        logger.info("[Transform] optimized complete summary=%s", summary)
        return summary
