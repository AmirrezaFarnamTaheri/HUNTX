from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from typing import Optional

from .connector import (
    MAX_DOWNLOAD_BYTES,
    TelegramUserConnector,
    TelegramUserItem,
    _UNWANTED_MEDIA_ATTRS,
    download_media_bounded,
)
from ..base import async_iter


@dataclass(frozen=True)
class WindowPage:
    items: list[TelegramUserItem]
    continuation_cursor: Optional[int]
    completed: bool
    scanned_messages: int


class WindowedTelegramUserConnector(TelegramUserConnector):
    """Read one bounded newest-to-oldest page from a UTC time window."""

    async def fetch_window_page(
        self,
        *,
        window_start_ts: int,
        window_end_ts: int,
        continuation_cursor: Optional[int],
        limit: int = 100,
        deadline: Optional[float] = None,
    ) -> WindowPage:
        if window_end_ts <= window_start_ts:
            raise ValueError("window_end_ts must be greater than window_start_ts")
        page_limit = max(1, min(int(limit), 1000))
        client = self._client()
        await self._ensure_connected_async(client)
        peer_entity = await self._resolve_peer_async(self.peer, client)

        offset_date = datetime.datetime.fromtimestamp(
            window_end_ts,
            tz=datetime.timezone.utc,
        )
        items: list[TelegramUserItem] = []
        scanned = 0
        last_message_id = continuation_cursor
        crossed_lower_boundary = False
        interrupted = False

        iterator = client.iter_messages(
            peer_entity,
            offset_date=offset_date,
            offset_id=continuation_cursor or 0,
            limit=page_limit,
            reverse=False,
        )
        async for msg in async_iter(iterator):
            if deadline is not None and time.time() >= deadline:
                interrupted = True
                break

            scanned += 1
            last_message_id = int(msg.id)
            timestamp = int(msg.date.timestamp())
            if timestamp < window_start_ts:
                crossed_lower_boundary = True
                break
            if timestamp >= window_end_ts:
                continue

            if any(getattr(msg, attr, None) for attr in _UNWANTED_MEDIA_ATTRS):
                continue

            text = msg.message or ""
            if text:
                items.append(
                    TelegramUserItem(
                        external_id=str(msg.id),
                        data=text.encode("utf-8", errors="ignore"),
                        metadata={
                            "filename": f"msg_{msg.id}.txt",
                            "timestamp": msg.date.timestamp(),
                            "is_text": True,
                            "window_start_ts": window_start_ts,
                            "window_end_ts": window_end_ts,
                        },
                    )
                )

            document = getattr(msg, "document", None)
            if not document:
                continue

            file_info = getattr(msg, "file", None)
            file_name = getattr(file_info, "name", None) or ""
            file_ext = getattr(file_info, "ext", None) or ""
            file_size = int(getattr(file_info, "size", 0) or 0)
            if file_name.lower().endswith(".apk") or file_ext.lower() == ".apk":
                continue
            if file_size > MAX_DOWNLOAD_BYTES:
                continue

            data = await download_media_bounded(client, msg)
            if not data:
                continue

            from ...utils.content_type import is_executable

            is_exec, _ = is_executable(data)
            if is_exec:
                continue

            filename = file_name or f"media_{msg.id}{file_ext}"
            items.append(
                TelegramUserItem(
                    external_id=f"{msg.id}_media",
                    data=data,
                    metadata={
                        "filename": filename,
                        "timestamp": msg.date.timestamp(),
                        "window_start_ts": window_start_ts,
                        "window_end_ts": window_end_ts,
                    },
                )
            )

        completed = not interrupted and (crossed_lower_boundary or scanned < page_limit or scanned == 0)
        next_cursor = None if completed else last_message_id
        return WindowPage(
            items=items,
            continuation_cursor=next_cursor,
            completed=completed,
            scanned_messages=scanned,
        )
