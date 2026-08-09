from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector
from ..state.ingestion_queue import IngestionWorkItem, PersistentIngestionQueue
from .ingest import IngestionPipeline

logger = logging.getLogger(__name__)


class WindowedIngestionPipeline:
    """Persist one MTProto page and its residue cursor in one transaction.

    A single entered connector is reused across pages that share Telegram
    credentials. Source rotation only changes the connector peer, eliminating
    the connect/disconnect cycle that previously occurred for every page.
    """

    def __init__(
        self,
        ingestion_pipeline: IngestionPipeline,
        work_queue: PersistentIngestionQueue,
    ) -> None:
        self.ingestion_pipeline = ingestion_pipeline
        self.work_queue = work_queue
        self._connector: Optional[WindowedTelegramUserConnector] = None
        self._connector_key: Optional[tuple[int, str, str]] = None
        self._connector_lock = asyncio.Lock()

    async def _close_unlocked(self, timeout: float) -> None:
        connector = self._connector
        self._connector = None
        self._connector_key = None
        if connector is None:
            return
        try:
            await asyncio.wait_for(
                connector.__aexit__(None, None, None),
                timeout=max(0.01, timeout),
            )
        except asyncio.TimeoutError:
            logger.error("Timed out closing reusable Telegram window connector")
        except Exception:
            logger.exception("Failed closing reusable Telegram window connector")

    async def close(self, timeout: float = 10.0) -> None:
        acquired = False
        try:
            await asyncio.wait_for(
                self._connector_lock.acquire(),
                timeout=max(0.01, timeout),
            )
            acquired = True
            await self._close_unlocked(timeout)
        except asyncio.TimeoutError:
            logger.error("Timed out acquiring reusable Telegram connector lock for close")
        finally:
            if acquired:
                self._connector_lock.release()

    async def invalidate(self, timeout: float = 10.0) -> None:
        """Drop a possibly unhealthy client after a page error or timeout."""
        await self.close(timeout)

    async def _connector_for(
        self,
        config: Any,
        deadline: Optional[float],
    ) -> WindowedTelegramUserConnector:
        key = (int(config.api_id), str(config.api_hash), str(config.session))
        if self._connector is None or self._connector_key != key:
            await self._close_unlocked(10.0)
            connector = WindowedTelegramUserConnector(
                api_id=config.api_id,
                api_hash=config.api_hash,
                session=config.session,
                peer=config.peer,
                state=None,
                fetch_windows=None,
            )
            connector.deadline = deadline
            await connector.__aenter__()
            self._connector = connector
            self._connector_key = key
        else:
            self._connector.peer = config.peer
            self._connector.deadline = deadline
        assert self._connector is not None
        return self._connector

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

        async with self._connector_lock:
            connector = await self._connector_for(config, deadline)
            connector.peer = config.peer
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
                lease_token=item.lease_token,
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
