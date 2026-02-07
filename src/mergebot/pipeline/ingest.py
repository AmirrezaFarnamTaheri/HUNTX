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

    def run(self, source_id: str, connector: SourceConnector, source_type: str = "telegram"):
        connector_name = connector.__class__.__name__
        logger.info(f"[Ingest] Starting ingestion for source: {source_id} (Type: {source_type}, Connector: {connector_name})")
        state = self.state_repo.get_source_state(source_id) or {}

        # Initialize or retrieve existing stats
        existing_stats = state.get("stats", {})
        total_files = existing_stats.get("total_files", 0)

        count = 0
        new_bytes = 0
        skipped_count = 0

        start_time = time.time()

        try:
            for item in connector.list_new(state):
                if self.state_repo.has_seen_file(source_id, item.external_id):
                    logger.debug(f"[Ingest] Skipping already seen file: {item.external_id} from {source_id}")
                    skipped_count += 1
                    continue

                filename = item.metadata.get("filename", "unknown")
                file_size = len(item.data)

                logger.info(f"[Ingest] Processing new file: {filename} (ID: {item.external_id}, Size: {file_size} bytes)")
                raw_hash = self.raw_store.save(item.data)

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

                if count % 10 == 0:
                    logger.info(f"[Ingest] Ingested {count} files so far from {source_id}...")

        except Exception as e:
            logger.exception(f"[Ingest] Error during ingestion for source {source_id}: {e}")
            raise

        duration = time.time() - start_time
        avg_size = (new_bytes / count) if count > 0 else 0

        # Update stats
        try:
            new_state = connector.get_state()

            # Merge stats into state
            new_state["stats"] = {
                "total_files": total_files + count,
                "last_run": {
                    "timestamp": time.time(),
                    "files_ingested": count,
                    "bytes_ingested": new_bytes,
                    "duration_seconds": duration,
                    "skipped_files": skipped_count
                }
            }

            self.state_repo.update_source_state(source_id, new_state, source_type=source_type)

            logger.info(
                f"[Ingest] Ingestion complete for {source_id}: "
                f"{count} new files ({new_bytes} bytes, Avg: {avg_size:.0f} bytes), {skipped_count} skipped, "
                f"took {duration:.2f}s."
            )

        except Exception as e:
            logger.exception(f"[Ingest] Failed to update state for source {source_id}: {e}")
