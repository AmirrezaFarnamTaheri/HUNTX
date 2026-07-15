from __future__ import annotations

from typing import Any, Optional

from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector
from ..state.ingestion_queue import IngestionWorkItem, PersistentIngestionQueue
from .ingest import IngestionPipeline


class WindowedIngestionPipeline:
    """Persist one MTProto page and its residue cursor in one transaction."""

    def __init__(
        self,
        ingestion_pipeline: IngestionPipeline,
        work_queue: PersistentIngestionQueue,
    ) -> None:
        self.ingestion_pipeline = ingestion_pipeline
        self.work_queue = work_queue

    async def run_page(
        self,
        source: Any,
        item: IngestionWorkItem,
        *,
        owner: str,
        deadline: Optional[float],
        page_size: int,
    ) -> dict[str, int | bool | None]:
        config = source.telegram_user
        if config is None:
            raise ValueError(f"source {source.id} is not an MTProto source")

        connector = WindowedTelegramUserConnector(
            api_id=config.api_id,
            api_hash=config.api_hash,
            session=config.session,
            peer=config.peer,
            state=None,
            fetch_windows=None,
        )
        connector.deadline = deadline

        async with connector:
            page = await connector.fetch_window_page(
                window_start_ts=item.window_start_ts,
                window_end_ts=item.window_end_ts,
                continuation_cursor=item.continuation_cursor,
                limit=page_size,
                deadline=deadline,
            )

        with self.ingestion_pipeline.state_repo.db.connect() as conn:
            count, new_bytes, skipped, text, media = self.ingestion_pipeline._process_batch(
                item.source_id,
                page.items,
                conn=conn,
            )
            self.work_queue.checkpoint_page(
                item.id,
                owner,
                continuation_cursor=page.continuation_cursor,
                items_ingested=count,
                bytes_ingested=new_bytes,
                completed=page.completed,
                conn=conn,
            )

        return {
            "completed": page.completed,
            "continuation_cursor": page.continuation_cursor,
            "scanned_messages": page.scanned_messages,
            "items_ingested": count,
            "bytes_ingested": new_bytes,
            "skipped_items": skipped,
            "text_items": text,
            "media_items": media,
        }
