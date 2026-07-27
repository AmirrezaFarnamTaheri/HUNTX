import json
import logging
import time
import concurrent.futures
from collections import Counter
from typing import Dict, Any, List, Tuple, Optional
from ..store.raw_store import RawStore
from ..state.repo import StateRepo
from ..formats.registry import FormatRegistry
from ..core.router import decide_format
from ..config.schema import SourceConfig

logger = logging.getLogger(__name__)

# How many files to process and flush to DB in one batch
TRANSFORM_BATCH_SIZE = 200


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
        self.max_workers = max_workers

    def _process_single_file(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Worker function to process a single file.
        Returns a dict with stats/results and accumulated record rows for batch insert.
        """
        file_start = time.time()
        raw_hash = row["raw_hash"]
        observation_id = int(row["id"])
        source_id = row["source_id"]
        filename = row["filename"] or "unknown"
        result: Dict[str, Any] = {
            "status": "ok",
            "format": None,
            "records": 0,
            "duration": 0.0,
            "record_rows": [],  # (raw_hash, observation_id, type, unique_hash, json)
            "status_update": None,  # (status, error_msg, observation_id)
            "raw_hash": raw_hash,
            "filename": filename,
        }

        try:
            data = self.raw_store.get(raw_hash)
            if not data:
                logger.warning(f"[Transform] Raw data missing for hash={raw_hash[:12]} file={filename}")
                result["status"] = "failed"
                result["status_update"] = ("failed", "Raw data missing", observation_id)
                return result

            # Decide format
            fmt_id = decide_format(filename, data)
            result["format"] = fmt_id

            # Check if format is allowed for this source
            source_conf = self.source_configs.get(source_id)
            if source_conf and source_conf.selector:
                allowed = source_conf.selector.include_formats
                if fmt_id not in allowed and "all" not in allowed:
                    logger.debug(
                        f"[Transform] Skipping {filename} from {source_id}: "
                        f"format '{fmt_id}' not in allowed={allowed}"
                    )
                    result["status"] = "skipped"
                    result["status_update"] = (
                        "ignored",
                        f"Format {fmt_id} not allowed",
                        observation_id,
                    )
                    return result

            # Check handler availability
            handler = self.registry.get(fmt_id)
            if not handler:
                logger.debug(f"[Transform] No handler for format={fmt_id} file={filename}")
                result["status"] = "failed"
                result["status_update"] = ("failed", f"No handler for {fmt_id}", observation_id)
                return result

            # Parse
            try:
                records = handler.parse(data, {"filename": filename, "source_id": source_id})
            except Exception as e:
                logger.warning(f"[Transform] Parse error file={filename} fmt={fmt_id}: {e}")
                result["status"] = "failed"
                result["status_update"] = (
                    "failed",
                    f"Parse error: {str(e)}",
                    observation_id,
                )
                return result

            # Accumulate record rows for batch insert (no DB call here)
            record_rows = []
            for rec in records:
                # Use default=str to safely handle non-serializable types (e.g. datetime)
                record_rows.append(
                    (
                        raw_hash,
                        observation_id,
                        fmt_id,
                        rec["unique_hash"],
                        json.dumps(rec["data"], default=str),
                    )
                )

            result["record_rows"] = record_rows
            result["records"] = len(record_rows)
            result["status_update"] = ("processed", None, observation_id)
            result["duration"] = time.time() - file_start
            return result

        except Exception as e:
            logger.error(f"[Transform] Unexpected error hash={raw_hash[:12]} file={filename}: {e}")
            result["status"] = "failed"
            result["status_update"] = ("failed", str(e), observation_id)
            return result

    def _flush_batch(self, results: List[Dict[str, Any]]) -> Tuple[int, int, int, int]:
        """Flush accumulated record rows and status updates to DB in batch.
        Returns (records_inserted, processed, failed, skipped)."""
        all_record_rows: List[tuple] = []
        status_updates: List[tuple] = []
        processed = failed = skipped = 0

        for res in results:
            if res["status_update"]:
                status_updates.append(res["status_update"])
            if res["status"] == "ok":
                all_record_rows.extend(res["record_rows"])
                processed += 1
            elif res["status"] == "failed":
                failed += 1
            elif res["status"] == "skipped":
                skipped += 1

        # Batch DB writes — both in ONE transaction.
        #
        # These previously ran through two separate connections, so each
        # committed independently. If the process died (or the status update
        # raised) after records committed but before the files left 'pending',
        # the next run re-fetched those files via get_pending_files, re-parsed
        # them, and inserted the same records again under new ids. Build-time
        # dedup hid the output impact, but `records` grew without bound and the
        # transform stage repeated that work every single run. Sharing one
        # connection makes the pair atomic: either both land or neither does.
        if all_record_rows or status_updates:
            with self.state_repo.db.connect() as conn:
                if all_record_rows:
                    self.state_repo.add_records_batch(all_record_rows, conn=conn)
                if status_updates:
                    self.state_repo.update_observation_status_batch(status_updates, conn=conn)

        return len(all_record_rows), processed, failed, skipped

    def process_pending(self):
        """
        Finds pending files, determines format, parses, and saves records.
        Processes in batches of TRANSFORM_BATCH_SIZE for efficient DB writes.
        Parallelized with ThreadPoolExecutor within each batch.
        """
        phase_start = time.time()
        total_processed = 0
        total_failed = 0
        total_skipped = 0
        total_records = 0
        format_counts: Counter = Counter()
        batch_num = 0

        logger.info(f"[Transform] ═══ Starting transformation ═══  batch_size={TRANSFORM_BATCH_SIZE}")

        # Reuse thread pool across batches to avoid overhead
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while True:
                # Fetch next batch of pending files
                batch = self.state_repo.get_pending_files(limit=TRANSFORM_BATCH_SIZE)
                if not batch:
                    break

                batch_num += 1
                batch_len = len(batch)
                batch_t0 = time.time()

                logger.info(f"[Transform] ── Batch {batch_num} ──  files={batch_len}")

                # Parallel parse within batch
                batch_results: List[Dict[str, Any]] = []
                future_to_row = {executor.submit(self._process_single_file, row): row for row in batch}

                for future in concurrent.futures.as_completed(future_to_row):
                    try:
                        res = future.result()
                        batch_results.append(res)
                        if res["format"]:
                            format_counts[res["format"]] += 1
                    except Exception as e:
                        logger.error(f"[Transform] Worker thread failed: {e}")

                # Flush batch to DB
                try:
                    flush_t0 = time.time()
                    records_inserted, processed, failed, skipped = self._flush_batch(batch_results)
                    flush_dur = time.time() - flush_t0
                except Exception as e:
                    logger.error(f"[Transform] Critical batch failure, aborting transform phase: {e}")
                    raise

                total_processed += processed
                total_failed += failed
                total_skipped += skipped
                total_records += records_inserted
                batch_dur = time.time() - batch_t0

                logger.info(
                    f"[Transform] ── Batch {batch_num} done ──  "
                    f"processed={processed} failed={failed} skipped={skipped}  "
                    f"records={records_inserted}  "
                    f"parse={batch_dur - flush_dur:.2f}s  flush={flush_dur:.2f}s  total={batch_dur:.2f}s"
                )

        phase_dur = time.time() - phase_start
        formats_summary = ", ".join(f"{k}:{v}" for k, v in sorted(format_counts.items(), key=lambda x: -x[1]))
        logger.info(
            f"[Transform] ═══ Transformation complete ═══  "
            f"processed={total_processed} failed={total_failed} skipped={total_skipped}  "
            f"records={total_records}  batches={batch_num}  "
            f"formats=[{formats_summary}]  duration={phase_dur:.2f}s"
        )
