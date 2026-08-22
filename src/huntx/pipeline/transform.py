import concurrent.futures
import json
import logging
import os
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ..config.schema import SourceConfig
from ..core.router import decide_format
from ..formats.registry import FormatRegistry
from ..state.repo import StateRepo
from ..store.raw_store import RawStore

logger = logging.getLogger(__name__)

TRANSFORM_BATCH_SIZE = 200
_DEFAULT_MAX_BATCHES = 1_000
_DEFAULT_MAX_RECORDS = 1_000_000
_DEFAULT_MAX_RECORDS_PER_FILE = 10_000


def _positive_limit(name: str, supplied: Optional[int], default: int, maximum: int) -> int:
    raw: Any = supplied if supplied is not None else os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        value = default
    if value < 1:
        logger.warning("Non-positive %s=%r; using %s", name, raw, default)
        value = default
    return min(value, maximum)


class TransformPipeline:
    def __init__(
        self,
        raw_store: RawStore,
        state_repo: StateRepo,
        registry: FormatRegistry,
        source_configs: Optional[Dict[str, SourceConfig]] = None,
        max_workers: int = 4,
    ):
        self.raw_store = raw_store
        self.state_repo = state_repo
        self.registry = registry
        self.source_configs = source_configs or {}
        self.max_workers = max(1, int(max_workers))
        self.max_records_per_file = _positive_limit(
            "HUNTX_TRANSFORM_MAX_RECORDS_PER_FILE",
            None,
            _DEFAULT_MAX_RECORDS_PER_FILE,
            _DEFAULT_MAX_RECORDS,
        )

    def _process_single_file(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse one pending observation without writing to the database."""
        file_start = time.monotonic()
        raw_hash = row["raw_hash"]
        observation_id = int(row.get("id") or 0)
        source_id = row["source_id"]
        filename = row["filename"] or "unknown"
        result: Dict[str, Any] = {
            "status": "ok",
            "format": None,
            "records": 0,
            "duration": 0.0,
            "record_rows": [],
            "status_update": None,
            "raw_hash": raw_hash,
            "filename": filename,
        }

        try:
            data = self.raw_store.get(raw_hash)
            if not data:
                logger.warning("[Transform] Raw data missing for hash=%s file=%s", raw_hash[:12], filename)
                result["status"] = "failed"
                result["status_update"] = ("failed", "Raw data missing", observation_id)
                return result

            fmt_id = decide_format(filename, data)
            result["format"] = fmt_id

            source_conf = self.source_configs.get(source_id)
            if source_conf and source_conf.selector:
                allowed = source_conf.selector.include_formats
                if fmt_id not in allowed and "all" not in allowed:
                    logger.debug(
                        "[Transform] Skipping %s from %s: format %r not in allowed=%s",
                        filename,
                        source_id,
                        fmt_id,
                        allowed,
                    )
                    result["status"] = "skipped"
                    result["status_update"] = (
                        "ignored",
                        f"Format {fmt_id} not allowed",
                        observation_id,
                    )
                    return result

            handler = self.registry.get(fmt_id)
            if not handler:
                logger.debug("[Transform] No handler for format=%s file=%s", fmt_id, filename)
                result["status"] = "failed"
                result["status_update"] = ("failed", f"No handler for {fmt_id}", observation_id)
                return result

            try:
                records = handler.parse(data, {"filename": filename, "source_id": source_id})
            except Exception as exc:
                logger.warning("[Transform] Parse error file=%s fmt=%s: %s", filename, fmt_id, exc)
                result["status"] = "failed"
                result["status_update"] = (
                    "failed",
                    f"Parse error: {exc}",
                    observation_id,
                )
                return result

            record_rows = []
            for index, record in enumerate(records):
                if index >= self.max_records_per_file:
                    result["status"] = "failed"
                    result["record_rows"] = []
                    result["records"] = 0
                    result["status_update"] = (
                        "failed",
                        "Transform record limit exceeded",
                        observation_id,
                    )
                    logger.error(
                        "[Transform] Record limit exceeded file=%s limit=%s",
                        filename,
                        self.max_records_per_file,
                    )
                    return result
                record_rows.append(
                    (
                        raw_hash,
                        observation_id,
                        fmt_id,
                        record["unique_hash"],
                        json.dumps(record["data"], default=str),
                    )
                )

            result["record_rows"] = record_rows
            result["records"] = len(record_rows)
            result["status_update"] = ("processed", None, observation_id)
            result["duration"] = time.monotonic() - file_start
            return result
        except Exception as exc:
            logger.error("[Transform] Unexpected error hash=%s file=%s: %s", raw_hash[:12], filename, exc)
            result["status"] = "failed"
            result["status_update"] = ("failed", str(exc), observation_id)
            return result

    def _flush_batch(self, results: List[Dict[str, Any]]) -> Tuple[int, int, int, int]:
        """Commit records and observation statuses in one transaction."""
        all_record_rows: List[tuple] = []
        status_updates: List[tuple] = []
        processed = failed = skipped = 0

        for result in results:
            if result["status_update"]:
                status_updates.append(result["status_update"])
            if result["status"] == "ok":
                all_record_rows.extend(result["record_rows"])
                processed += 1
            elif result["status"] == "failed":
                failed += 1
            elif result["status"] == "skipped":
                skipped += 1

        if all_record_rows or status_updates:
            with self.state_repo.db.connect() as conn:
                if all_record_rows:
                    self.state_repo.add_records_batch(all_record_rows, conn=conn)
                if status_updates:
                    self.state_repo.update_observation_status_batch(status_updates, conn=conn)

        return len(all_record_rows), processed, failed, skipped

    def process_pending(
        self,
        *,
        deadline_monotonic: Optional[float] = None,
        max_batches: Optional[int] = None,
        max_records: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Transform pending observations under explicit work and time bounds.

        A result with ``completed=False`` is never a successful drain. Pending
        observations that were parsed but not committed because the global
        record budget was reached remain pending for a later run.
        """
        phase_start = time.monotonic()
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
        total_processed = 0
        total_failed = 0
        total_skipped = 0
        total_records = 0
        deferred = 0
        format_counts: Counter = Counter()
        batch_num = 0
        stop_reason = "complete"

        logger.info(
            "[Transform] Starting transformation batch_size=%s max_batches=%s max_records=%s",
            TRANSFORM_BATCH_SIZE,
            batch_limit,
            record_limit,
        )

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            while True:
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                    stop_reason = "deadline"
                    break
                if batch_num >= batch_limit:
                    stop_reason = "max_batches"
                    break
                if total_records >= record_limit:
                    stop_reason = "max_records"
                    break

                batch = self.state_repo.get_pending_files(limit=TRANSFORM_BATCH_SIZE)
                if not batch:
                    break

                batch_num += 1
                batch_start = time.monotonic()
                futures = {executor.submit(self._process_single_file, row): row for row in batch}
                timeout = None
                if deadline_monotonic is not None:
                    timeout = max(0.0, deadline_monotonic - time.monotonic())
                done, not_done = concurrent.futures.wait(futures, timeout=timeout)
                if not_done:
                    for future in not_done:
                        future.cancel()
                    stop_reason = "deadline"

                batch_results: List[Dict[str, Any]] = []
                for future in done:
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error("[Transform] Worker thread failed: %s", exc)
                        continue
                    batch_results.append(result)
                    if result["format"]:
                        format_counts[result["format"]] += 1

                remaining_records = record_limit - total_records
                commit_results: List[Dict[str, Any]] = []
                selected_records = 0
                for result in batch_results:
                    generated = int(result.get("records", 0)) if result.get("status") == "ok" else 0
                    if generated > remaining_records - selected_records:
                        deferred += 1
                        stop_reason = "max_records"
                        continue
                    commit_results.append(result)
                    selected_records += generated

                records_inserted = processed = failed = skipped = 0
                if commit_results:
                    records_inserted, processed, failed, skipped = self._flush_batch(commit_results)
                total_processed += processed
                total_failed += failed
                total_skipped += skipped
                total_records += records_inserted

                logger.info(
                    "[Transform] Batch %s done files=%s committed=%s deferred=%s "
                    "processed=%s failed=%s skipped=%s records=%s duration=%.2fs",
                    batch_num,
                    len(batch),
                    len(commit_results),
                    len(batch_results) - len(commit_results),
                    processed,
                    failed,
                    skipped,
                    records_inserted,
                    time.monotonic() - batch_start,
                )
                if stop_reason != "complete":
                    break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        summary = {
            "completed": stop_reason == "complete",
            "stop_reason": stop_reason,
            "processed": total_processed,
            "failed": total_failed,
            "skipped": total_skipped,
            "records": total_records,
            "batches": batch_num,
            "deferred": deferred,
            "duration_seconds": time.monotonic() - phase_start,
            "formats": dict(format_counts),
        }
        logger.info("[Transform] Final summary: %s", summary)
        return summary
