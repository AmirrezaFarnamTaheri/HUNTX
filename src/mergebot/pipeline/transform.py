import logging
import time
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

    def process_pending(self):
        """
        Finds pending files, determines format, parses, and saves records.
        """
        pending_files = self.state_repo.get_pending_files()
        total_pending = len(pending_files)

        logger.info(f"[Transform] Starting transformation: found {total_pending} pending files.")

        processed_count = 0
        failed_count = 0
        skipped_count = 0
        format_counts = Counter()

        for row in pending_files:
            file_start = time.time()
            raw_hash = row["raw_hash"]
            source_id = row["source_id"]
            filename = row["filename"] or "unknown"

            logger.debug(f"[Transform] Transforming file: {filename} (hash: {raw_hash}) from source: {source_id}")

            try:
                data = self.raw_store.get(raw_hash)
                if not data:
                    logger.error(f"[Transform] Raw data missing for {raw_hash}")
                    self.state_repo.update_file_status(raw_hash, "failed", "Raw data missing")
                    failed_count += 1
                    continue

                # Decide format
                fmt_id = decide_format(filename, data)
                logger.debug(f"[Transform] Detected format {fmt_id} for file {filename}")

                # Check if format is allowed for this source
                source_conf = self.source_configs.get(source_id)
                if source_conf and source_conf.selector:
                    allowed = source_conf.selector.include_formats
                    if fmt_id not in allowed and "all" not in allowed:
                         logger.info(f"[Transform] Skipping file {filename} from {source_id}: Format {fmt_id} not in allowed list {allowed}")
                         self.state_repo.update_file_status(raw_hash, "ignored", f"Format {fmt_id} not allowed")
                         skipped_count += 1
                         continue

                format_counts[fmt_id] += 1

                handler = self.registry.get(fmt_id)
                if not handler:
                    logger.warning(f"[Transform] No handler registered for format: {fmt_id}")
                    self.state_repo.update_file_status(raw_hash, "failed", f"No handler for {fmt_id}")
                    failed_count += 1
                    continue

                records = handler.parse(data, {"filename": filename, "source_id": source_id})
                record_count = len(records)
                logger.debug(f"[Transform] Parsed {record_count} records from {filename}")

                # Save records
                for rec in records:
                    self.state_repo.add_record(
                        raw_hash=raw_hash,
                        record_type=fmt_id,
                        unique_hash=rec["unique_hash"],
                        data=rec["data"]
                    )

                self.state_repo.update_file_status(raw_hash, "processed")
                processed_count += 1

                file_duration = time.time() - file_start
                if file_duration > 0.5:
                    logger.warning(f"[Transform] Slow transform for {filename}: {file_duration:.2f}s")

            except Exception as e:
                logger.exception(f"[Transform] Failed to transform file {raw_hash} (file: {filename}): {type(e).__name__} - {e}")
                self.state_repo.update_file_status(raw_hash, "failed", str(e))
                failed_count += 1

        formats_summary = ", ".join([f"{k}: {v}" for k, v in format_counts.items()])
        logger.info(
            f"[Transform] Transformation complete. "
            f"Processed: {processed_count}, Failed: {failed_count}, Skipped: {skipped_count}, "
            f"Formats: [{formats_summary}], Total Pending: {total_pending}."
        )
