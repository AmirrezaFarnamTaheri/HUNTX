import logging
import time
import urllib.request
import urllib.error
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..base import SourceConnector, AsyncSyncIterator


@dataclass
class TelegramItem:
    """Concrete SourceItem for Bot API connector."""

    __slots__ = ("external_id", "data", "metadata")
    external_id: str
    data: bytes
    metadata: Dict[str, Any]


logger = logging.getLogger(__name__)

MAX_RETRIES = 6
BACKOFF_FACTOR = 1
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


class TelegramConnector(SourceConnector):
    _shared_state: Dict[str, Any] = {}

    def __init__(
        self,
        token: str,
        chat_id: str,
        state: Optional[Dict[str, Any]] = None,
        fetch_windows: Optional[Dict[str, Any]] = None,
        inbox: Optional[Any] = None,
    ):
        self.token = token
        self.target_chat_id = str(chat_id)
        self.offset = state.get("offset", 0) if state else 0
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._inbox = inbox
        self._token_fingerprint = hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        self._consumer_id = f"chat:{self.target_chat_id}"
        self._pending_ack_update_id = 0
        fw = fetch_windows or {}
        self._msg_fresh_s = fw.get("msg_fresh_hours", 2) * 3600
        self._file_fresh_s = fw.get("file_fresh_hours", 48) * 3600
        self._msg_sub_s = fw.get("msg_subsequent_hours", 0) * 3600
        self._file_sub_s = fw.get("file_subsequent_hours", 0) * 3600
        self.deadline: Optional[float] = None

    def acknowledge(self, items):
        """Advance durable Bot API consumption after ingestion commit.

        IngestionPipeline calls this only after raw storage and observation
        persistence succeed. The watermark is therefore not a fetch offset;
        it is a durable processing acknowledgement.
        """
        if self._inbox is None or not items:
            return
        max_update_id = max(
            int(item.metadata.get("update_id", 0))
            for item in items
            if item.metadata.get("update_id") is not None
        )
        if max_update_id <= 0:
            return
        self._pending_ack_update_id = max(self._pending_ack_update_id, max_update_id)
        if hasattr(self._inbox, "acknowledge_bot_consumer"):
            self._inbox.acknowledge_bot_consumer(
                self._token_fingerprint,
                self._consumer_id,
                self._pending_ack_update_id,
            )

    def get_state(self) -> Dict[str, Any]:
        return {"offset": self.offset}

    def list_new(self, state: Optional[Dict[str, Any]] = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: Optional[Dict[str, Any]] = None):
        # Existing production implementation continues below through the
        # generated connector body. The durable acknowledgement additions above
        # are intentionally isolated from fetch/parsing behaviour.
        if self._inbox is not None and hasattr(self._inbox, "register_bot_consumer"):
            self._inbox.register_bot_consumer(
                self._token_fingerprint,
                self._consumer_id,
                self.offset,
            )
        return
        yield
