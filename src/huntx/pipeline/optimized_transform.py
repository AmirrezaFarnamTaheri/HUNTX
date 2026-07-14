from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from collections import Counter
from typing import Any, Optional

from .transform import TRANSFORM_BATCH_SIZE, TransformPipeline

logger = logging.getLogger(__name__)


class OptimizedTransformPipeline(TransformPipeline):
    """Adaptive transform loop with deadline checkpoints and fewer DB round trips."""

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
        deadline: Optional[float] = None,
        max_batches: Optional[int] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        batch_size = self._effective_batch_size()
        totals = {"processed": 0, "failed": 0, "skipped": 0, "records": 0}
        formats: Counter[str] = Counter()
        batches = 0
        deadline_exhausted = False

        logger.info(
            "[Transform] optimized start workers=%s batch_size=%s deadline=%s",
            self.max_workers,
            batch_size,
            deadline,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, self.max_workers)) as pool:
            while max_batches is None or batches < max_batches:
                if deadline is not None and time.monotonic() >= deadline:
                    deadline_exhausted = True
                    break
                batch = self.state_repo.get_pending_files(limit=batch_size)
                if not batch:
                    break
                batches += 1
                futures = [pool.submit(self._process_single_file, row) for row in batch]
                results: list[dict[str, Any]] = []
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    results.append(result)
                    format_id = result.get("format")
                    if isinstance(format_id, str):
                        formats[format_id] += 1
                records, processed, failed, skipped = self._flush_batch(results)
                totals["records"] += records
                totals["processed"] += processed
                totals["failed"] += failed
                totals["skipped"] += skipped
                logger.info(
                    "[Transform] optimized batch=%s files=%s totals=%s",
                    batches,
                    len(batch),
                    totals,
                )

        summary: dict[str, Any] = {
            **totals,
            "batches": batches,
            "batch_size": batch_size,
            "deadline_exhausted": deadline_exhausted,
            "duration_seconds": round(time.monotonic() - started, 3),
            "formats": dict(formats),
        }
        logger.info("[Transform] optimized complete summary=%s", summary)
        return summary
