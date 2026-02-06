import logging
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

        for row in pending_files:
            raw_hash = row["raw_hash"]
            source_id = row["source_id"]
            filename = row["filename"] or "unknown"

            try:
                data = self.raw_store.get(raw_hash)
                if not data:
                    self.state_repo.update_file_status(raw_hash, "failed", "Raw data missing")
                    continue

                # Decide format
                fmt_id = decide_format(filename, data)

                # Check if format is allowed for this source
                source_conf = self.source_configs.get(source_id)
                if source_conf and source_conf.selector:
                    allowed = source_conf.selector.include_formats
                    if fmt_id not in allowed and "all" not in allowed:
                         self.state_repo.update_file_status(raw_hash, "ignored", f"Format {fmt_id} not allowed")
                         continue

                handler = self.registry.get(fmt_id)
                records = handler.parse(data, {"filename": filename, "source_id": source_id})

                # Save records
                for rec in records:
                    self.state_repo.add_record(
                        raw_hash=raw_hash,
                        record_type=fmt_id,
                        unique_hash=rec["unique_hash"],
                        data=rec["data"]
                    )

                self.state_repo.update_file_status(raw_hash, "processed")

            except Exception as e:
                logger.exception(f"Failed to transform file {raw_hash}")
                self.state_repo.update_file_status(raw_hash, "failed", str(e))
