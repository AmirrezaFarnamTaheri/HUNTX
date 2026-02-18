import logging
import time
from ..connectors.base import SourceConnector
from ..store.raw_store import RawStore
from ..state.repo import StateRepo

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, raw_store: RawStore, state_repo: StateRepo):
        self.raw_store = raw_store
        self.state_repo = state_repo



    def _process_batch(self, source_id, buffer, conn):
        if not buffer:
            return 0, 0, 0, 0, 0  # processed, new_bytes, skipped, text, media

        # 1. Check seen files in batch
        external_ids = [item.external_id for item in buffer]
        seen_ids = self.state_repo.get_seen_files_batch(source_id, external_ids, conn=conn)

        records_to_insert = []
        new_items_count = 0
        new_bytes = 0
        skipped_count = 0
        text_count = 0
        media_count = 0

        for item in buffer:
            if item.external_id in seen_ids:
                skipped_count += 1
                continue

            filename = item.metadata.get("filename", "unknown")
            file_size = len(item.data)
            is_text = item.metadata.get("is_text", False) or filename.endswith(".txt")

            if is_text:
                text_count += 1
            else:
                media_count += 1

            raw_hash = self.raw_store.save(item.data)

            records_to_insert.append((
                source_id,
                item.external_id,
                raw_hash,
                file_size,
                filename,
                "pending",
                item.metadata,  # metadata will be json.dumps inside record_files_batch
            ))
            new_items_count += 1
            new_bytes += file_size

        if records_to_insert:
            # Note: record_files_batch handles json serialization of metadata
            # But wait, record_files_batch expects tuples. We should adjust record_files_batch to handle serialization or do it here.
            # Looking at StateRepo.record_file, it calls json.dumps.
            # But StateRepo.record_files_batch we added does NOT call json.dumps on the tuple item.
            # We need to serialize here.
            import json
            serialized_records = []
            for r in records_to_insert:
                # r is (source_id, external_id, raw_hash, file_size, filename, status, metadata)
                serialized_records.append((
                    r[0], r[1], r[2], r[3], r[4], r[5], json.dumps(r[6] or {})
                ))

            self.state_repo.record_files_batch(serialized_records, conn=conn)

        return new_items_count, new_bytes, skipped_count, text_count, media_count

    def run(self, source_id: str, connector: SourceConnector, source_type: str = "telegram", deadline: float = None):
        connector_name = connector.__class__.__name__
        logger.info(
            f"[Ingest] ═══ Starting source {source_id} ═══  "
            f"type={source_type}  connector={connector_name}"
        )

        # Optimization: Open DB connection once for the entire pipeline run
        with self.state_repo.db.connect() as conn:
            state = self.state_repo.get_source_state(source_id, conn=conn) or {}
            offset = state.get("offset", 0)
            existing_stats = state.get("stats", {})
            total_files = existing_stats.get("total_files", 0)
            last_run = existing_stats.get("last_run", {})

            logger.info(
                f"[Ingest] State: offset={offset}  total_files_so_far={total_files}  "
                f"last_run_files={last_run.get('files_ingested', '?')}  "
                f"last_run_skipped={last_run.get('skipped_files', '?')}"
            )

            count = 0
            new_bytes = 0
            skipped_count = 0
            text_count = 0
            media_count = 0

            start_time = time.time()

            try:
                logger.info(f"[Ingest] Requesting items from connector for {source_id}...")
                buffer = []
                BATCH_SIZE = 100

                for item in connector.list_new(state):
                    if deadline and time.time() > deadline:
                        logger.warning(f"[Ingest] Deadline exceeded for {source_id}. Interrupting ingestion.")
                        break

                    buffer.append(item)
                    if len(buffer) >= BATCH_SIZE:
                        c, nb, sc, tc, mc = self._process_batch(source_id, buffer, conn)
                        count += c
                        new_bytes += nb
                        skipped_count += sc
                        text_count += tc
                        media_count += mc
                        buffer = []

                        # Progress logging
                        if count > 0 and count % 25 == 0: # Approximation for logging frequency
                             elapsed = time.time() - start_time
                             rate = count / elapsed if elapsed > 0 else 0
                             logger.info(
                                 f"[Ingest] … {source_id}: {count} ingested "
                                 f"({new_bytes / 1024:.1f} KB, {rate:.1f} items/s)  "
                                 f"skipped={skipped_count}"
                             )

                if buffer:
                    c, nb, sc, tc, mc = self._process_batch(source_id, buffer, conn)
                    count += c
                    new_bytes += nb
                    skipped_count += sc
                    text_count += tc
                    media_count += mc
                    buffer = []

            except Exception as e:
                logger.exception(
                    f"[Ingest] Error during ingestion for {source_id} after {count} items: {e}"
                )
                raise

            duration = time.time() - start_time
            avg_size = (new_bytes / count) if count > 0 else 0
            rate = count / duration if duration > 0 else 0

            # Update stats
            try:
                new_state = connector.get_state()

                new_state["stats"] = {
                    "total_files": total_files + count,
                    "last_run": {
                        "timestamp": time.time(),
                        "files_ingested": count,
                        "bytes_ingested": new_bytes,
                        "duration_seconds": round(duration, 2),
                        "skipped_files": skipped_count,
                        "text_items": text_count,
                        "media_items": media_count,
                    },
                }

                self.state_repo.update_source_state(source_id, new_state, source_type=source_type, conn=conn)

                logger.info(
                    f"[Ingest] ═══ Done {source_id} ═══  "
                    f"new={count} (text={text_count} media={media_count})  "
                    f"size={new_bytes / 1024:.1f} KB (avg={avg_size:.0f} B)  "
                    f"skipped={skipped_count}  rate={rate:.1f}/s  duration={duration:.2f}s"
                )

                if count == 0 and skipped_count == 0:
                    logger.warning(
                        f"[Ingest] Zero items from {source_id}. "
                        f"Check connector logs for filtered/ignored updates."
                    )

            except Exception as e:
                logger.exception(f"[Ingest] Failed to update state for {source_id}: {e}")
                raise
