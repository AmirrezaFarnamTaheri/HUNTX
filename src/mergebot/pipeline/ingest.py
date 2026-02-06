import logging
import time
from typing import Dict, Any
from ..connectors.base import SourceConnector
from ..store.raw_store import RawStore
from ..state.repo import StateRepo

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self, raw_store: RawStore, state_repo: StateRepo):
        self.raw_store = raw_store
        self.state_repo = state_repo

    def run(self, source_id: str, connector: SourceConnector):
        state = self.state_repo.get_source_state(source_id) or {}

        # Initialize or retrieve existing stats
        existing_stats = state.get("stats", {})
        total_files = existing_stats.get("total_files", 0)

        count = 0
        new_bytes = 0

        start_time = time.time()

        for item in connector.list_new(state):
            if self.state_repo.has_seen_file(source_id, item.external_id):
                continue

            raw_hash = self.raw_store.save(item.data)

            filename = item.metadata.get("filename", "unknown")
            file_size = len(item.data)

            self.state_repo.record_file(
                source_id=source_id,
                external_id=item.external_id,
                raw_hash=raw_hash,
                file_size=file_size,
                filename=filename,
                status="pending",
                metadata=item.metadata  # Pass metadata
            )
            count += 1
            new_bytes += file_size

        duration = time.time() - start_time

        # Update stats
        new_state = connector.get_state()

        # Merge stats into state
        new_state["stats"] = {
            "total_files": total_files + count,
            "last_run": {
                "timestamp": time.time(),
                "files_ingested": count,
                "bytes_ingested": new_bytes,
                "duration_seconds": duration
            }
        }

        self.state_repo.update_source_state(source_id, new_state, source_type="telegram")

        if count > 0:
            logger.info(f"Ingested {count} new files from {source_id} ({new_bytes} bytes)")
