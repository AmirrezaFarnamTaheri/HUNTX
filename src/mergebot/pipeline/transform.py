import logging
import time
import concurrent.futures
from collections import Counter
from typing import Dict, Any, Optional
from ..store.raw_store import RawStore
from ..state.repo import StateRepo
from ..formats.registry import FormatRegistry
from ..core.router import decide_format
from ..config.schema import SourceConfig

logger = logging.getLogger(__name__)

class TransformPipeline:
    def __init__(self, raw_store: RawStore, state_repo: StateRepo, registry: FormatRegistry, source_configs: Dict[str, SourceConfig] = {}):
        self.raw_store = raw_store
        self.state_repo = state_repo
        self.registry = registry
        self.source_configs = source_configs

    def _process_single_file(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Worker function to process a single file.
        Returns a dict with stats/results.
        """
        file_start = time.time()
        raw_hash = row["raw_hash"]
        source_id = row["source_id"]
        filename = row["filename"] or "unknown"
        file_size_bytes = row.get("file_size", 0)

        result = {
            "status": "ok",
            "format": None,
            "records": 0,
            "duration": 0
        }

        # logger.debug(f"[Transform] Processing file: {filename} (hash: {raw_hash})")

        try:
            data = self.raw_store.get(raw_hash)
            if not data:
                logger.error(f"[Transform] Raw data missing for {raw_hash} (file: {filename})")
                self.state_repo.update_file_status(raw_hash, "failed", "Raw data missing")
                result["status"] = "failed"
                return result

            # Decide format
            fmt_id = decide_format(filename, data)
            result["format"] = fmt_id

            # Check if format is allowed for this source
            source_conf = self.source_configs.get(source_id)
            if source_conf and source_conf.selector:
                allowed = source_conf.selector.include_formats
                if fmt_id not in allowed and "all" not in allowed:
                     logger.info(f"[Transform] Skipping file {filename} from {source_id}: Format '{fmt_id}' not in allowed list {allowed}")
                     self.state_repo.update_file_status(raw_hash, "ignored", f"Format {fmt_id} not allowed")
                     result["status"] = "skipped"
                     return result

            # Check handler availability
            handler = self.registry.get(fmt_id)
            if not handler:
                logger.warning(f"[Transform] No handler registered for format: {fmt_id} (File: {filename})")
                self.state_repo.update_file_status(raw_hash, "failed", f"No handler for {fmt_id}")
                result["status"] = "failed"
                return result

            # Parse
            try:
                records = handler.parse(data, {"filename": filename, "source_id": source_id})
            except Exception as e:
                logger.error(f"[Transform] Parse error in {filename} (Format: {fmt_id}): {e}")
                self.state_repo.update_file_status(raw_hash, "failed", f"Parse error: {str(e)}")
                result["status"] = "failed"
                return result

            # Save records
            # Note: SQLite writes from threads are safe if connection timeout is high (which we set to 30s)
            # and we are using one repo instance (which uses new connections per call).
            saved_records = 0
            for rec in records:
                self.state_repo.add_record(
                    raw_hash=raw_hash,
                    record_type=fmt_id,
                    unique_hash=rec["unique_hash"],
                    data=rec["data"]
                )
                saved_records += 1

            self.state_repo.update_file_status(raw_hash, "processed")

            result["records"] = saved_records
            result["duration"] = time.time() - file_start
            return result

        except Exception as e:
            logger.exception(f"[Transform] Unexpected error transforming file {raw_hash} (file: {filename}): {e}")
            self.state_repo.update_file_status(raw_hash, "failed", str(e))
            result["status"] = "failed"
            return result

    def process_pending(self):
        """
        Finds pending files, determines format, parses, and saves records.
        Parallelized with ThreadPoolExecutor.
        """
        pending_files = self.state_repo.get_pending_files()
        total_pending = len(pending_files)

        if total_pending == 0:
            logger.info("[Transform] No pending files to process.")
            return

        logger.info(f"[Transform] Starting transformation: found {total_pending} pending files.")

        processed_count = 0
        failed_count = 0
        skipped_count = 0
        format_counts = Counter()

        # Use ThreadPoolExecutor
        # Max workers = 3 (safe balance)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_file = {executor.submit(self._process_single_file, row): row for row in pending_files}

            for future in concurrent.futures.as_completed(future_to_file):
                res = future.result()

                if res["status"] == "ok":
                    processed_count += 1
                    format_counts[res["format"]] += 1
                elif res["status"] == "failed":
                    failed_count += 1
                elif res["status"] == "skipped":
                    skipped_count += 1

        formats_summary = ", ".join([f"{k}: {v}" for k, v in format_counts.items()])
        logger.info(
            f"[Transform] Transformation complete. "
            f"Processed: {processed_count}, Failed: {failed_count}, Skipped: {skipped_count}, "
            f"Formats: [{formats_summary}], Total Pending: {total_pending}."
        )
