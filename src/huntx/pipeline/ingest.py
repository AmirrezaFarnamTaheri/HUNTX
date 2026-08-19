import hashlib
import json
import logging
import time
from typing import Optional

from ..connectors.base import SourceConnector, maybe_await
from ..state.repo import StateRepo
from ..store.raw_store import RawStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, raw_store: RawStore, state_repo: StateRepo):
        self.raw_store = raw_store
        self.state_repo = state_repo

    @staticmethod
    def _existing_content_hashes(source_id, hashes, conn):
        """Return source-local raw hashes already persisted for content identity.

        This compatibility lookup is deliberately opt-in at the connector item
        level. It lets V2Ray rows written with historical 16/32-character,
        index-dependent external IDs remain deduplicated after the identity
        scheme changes, without changing identity semantics for other sources.
        """
        unique_hashes = sorted(set(hashes))
        if not unique_hashes:
            return set()
        placeholders = ",".join("?" for _ in unique_hashes)
        cursor = conn.execute(
            f"SELECT DISTINCT raw_hash FROM seen_files "
            f"WHERE source_id = ? AND raw_hash IN ({placeholders})",
            [source_id, *unique_hashes],
        )
        return {row[0] for row in cursor.fetchall()}

    def _process_batch(self, source_id, buffer, conn=None):
        if not buffer:
            return 0, 0, 0, 0, 0  # processed, new_bytes, skipped, text, media

        if conn is None:
            with self.state_repo.db.connect() as batch_conn:
                return self._process_batch(source_id, buffer, batch_conn)

        prepared = [(item, hashlib.sha256(item.data).hexdigest()) for item in buffer]
        external_ids = [item.external_id for item, _ in prepared]
        seen_hashes = self.state_repo.get_seen_file_hashes_batch(
            source_id, external_ids, conn=conn
        )

        content_identity_hashes = [
            item_hash
            for item, item_hash in prepared
            if bool((getattr(item, "metadata", None) or {}).get("dedupe_by_content"))
        ]
        existing_content_hashes = self._existing_content_hashes(
            source_id, content_identity_hashes, conn
        )
        content_hashes_seen_in_batch: set[str] = set()

        records_to_insert = []
        new_items_count = 0
        new_bytes = 0
        skipped_count = 0
        text_count = 0
        media_count = 0

        for item, item_hash in prepared:
            metadata = getattr(item, "metadata", None) or {}
            dedupe_by_content = bool(metadata.get("dedupe_by_content"))

            if seen_hashes.get(str(item.external_id)) == item_hash:
                skipped_count += 1
                continue

            if dedupe_by_content and (
                item_hash in existing_content_hashes
                or item_hash in content_hashes_seen_in_batch
            ):
                skipped_count += 1
                continue

            filename = metadata.get("filename", "unknown")
            file_size = len(item.data)
            is_text = metadata.get("is_text", False) or filename.endswith(".txt")

            if is_text:
                text_count += 1
            else:
                media_count += 1

            raw_hash = self.raw_store.save(item.data)
            records_to_insert.append(
                (
                    source_id,
                    item.external_id,
                    raw_hash,
                    file_size,
                    filename,
                    "pending",
                    metadata,
                )
            )
            if dedupe_by_content:
                content_hashes_seen_in_batch.add(item_hash)
            new_items_count += 1
            new_bytes += file_size

        if records_to_insert:
            serialized_records = []
            for record in records_to_insert:
                serialized_records.append(
                    (
                        record[0],
                        record[1],
                        record[2],
                        record[3],
                        record[4],
                        record[5],
                        json.dumps(record[6] or {}),
                    )
                )
            self.state_repo.record_files_batch(serialized_records, conn=conn)

        return new_items_count, new_bytes, skipped_count, text_count, media_count

    async def run(
        self,
        source_id: str,
        connector: SourceConnector,
        source_type: str = "telegram",
        deadline: Optional[float] = None,
    ):
        connector_name = connector.__class__.__name__
        logger.info(
            f"[Ingest] ═══ Starting source {source_id} ═══  "
            f"type={source_type}  connector={connector_name}"
        )

        state = self.state_repo.get_source_state(source_id) or {}
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
            logger.info("[Ingest] Requesting items from connector for %s...", source_id)
            buffer = []
            batch_size = 100

            async def iterate_items():
                items_iter = connector.list_new(state)
                if hasattr(items_iter, "__aiter__"):
                    async for item in items_iter:
                        yield item
                else:
                    for item in items_iter:
                        yield item

            async for item in iterate_items():
                if deadline and time.time() > deadline:
                    logger.warning(
                        "[Ingest] Deadline exceeded for %s. Interrupting ingestion.",
                        source_id,
                    )
                    break

                buffer.append(item)
                if len(buffer) >= batch_size:
                    committed = buffer
                    c, nb, sc, tc, mc = self._process_batch(source_id, committed)
                    acknowledge = getattr(connector, "acknowledge", None)
                    if acknowledge is not None:
                        await maybe_await(acknowledge(committed))
                    count += c
                    new_bytes += nb
                    skipped_count += sc
                    text_count += tc
                    media_count += mc
                    buffer = []

                    if count > 0 and count % 25 == 0:
                        elapsed = time.time() - start_time
                        rate = count / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"[Ingest] … {source_id}: {count} ingested "
                            f"({new_bytes / 1024:.1f} KB, {rate:.1f} items/s)  "
                            f"skipped={skipped_count}"
                        )

            if buffer:
                committed = buffer
                c, nb, sc, tc, mc = self._process_batch(source_id, committed)
                acknowledge = getattr(connector, "acknowledge", None)
                if acknowledge is not None:
                    await maybe_await(acknowledge(committed))
                count += c
                new_bytes += nb
                skipped_count += sc
                text_count += tc
                media_count += mc

        except Exception as exc:
            logger.exception(
                "[Ingest] Error during ingestion for %s after %s items: %s",
                source_id,
                count,
                exc,
            )
            raise

        duration = time.time() - start_time
        avg_size = (new_bytes / count) if count > 0 else 0
        rate = count / duration if duration > 0 else 0

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

            self.state_repo.update_source_state(
                source_id, new_state, source_type=source_type
            )

            commit_acknowledgement = getattr(connector, "commit_acknowledgement", None)
            if commit_acknowledgement is not None:
                await maybe_await(commit_acknowledgement())

            logger.info(
                f"[Ingest] ═══ Done {source_id} ═══  "
                f"new={count} (text={text_count} media={media_count})  "
                f"size={new_bytes / 1024:.1f} KB (avg={avg_size:.0f} B)  "
                f"skipped={skipped_count}  rate={rate:.1f}/s  duration={duration:.2f}s"
            )

            if count == 0 and skipped_count == 0:
                logger.warning(
                    "[Ingest] Zero items from %s. Check connector logs for "
                    "filtered/ignored updates.",
                    source_id,
                )

        except Exception as exc:
            logger.exception("[Ingest] Failed to update state for %s: %s", source_id, exc)
            raise
