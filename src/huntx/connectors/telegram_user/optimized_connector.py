from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator

from ..base import async_iter, maybe_await
from .connector import (
    InputMessagesFilterDocument,
    StringSession,
    TelegramClient,
    TelegramUserConnector,
    TelegramUserItem,
    _TEXT_BATCH_SIZE,
    _UNWANTED_MEDIA_ATTRS,
)

logger = logging.getLogger(__name__)


class OptimizedTelegramUserConnector(TelegramUserConnector):
    """MTProto connector with isolated clients and bounded window scans."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._owned_client: Any = None
        raw_timeout = os.environ.get("HUNTX_MEDIA_DOWNLOAD_TIMEOUT", "45")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 45.0
        self._download_timeout = max(5.0, min(timeout, 300.0))

    def _client(self) -> Any:
        if self._owned_client is None:
            if TelegramClient is None or StringSession is None:
                raise RuntimeError("Telethon is required for telegram_user sources")
            self._owned_client = TelegramClient(
                StringSession(self.session), self.api_id, self.api_hash
            )
        return self._owned_client

    async def __a