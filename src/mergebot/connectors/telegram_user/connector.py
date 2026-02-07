import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Iterator
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon import utils
from ..base import SourceConnector

logger = logging.getLogger(__name__)

@dataclass
class SourceItem:
    external_id: str
    data: bytes
    metadata: Dict[str, Any]

class TelegramUserConnector:
    _shared_clients = {}  # key by (api_id, session)

    def __init__(self, api_id: int, api_hash: str, session: str, peer: str, state: Optional[Dict[str, Any]] = None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self.peer = peer  # "@channel" or "-100123..."
        self.offset = (state or {}).get("offset", 0)

    def _client(self) -> TelegramClient:
        key = (self.api_id, self.session)
        if key not in self._shared_clients:
            logger.info(f"Initializing new Telegram User Client for api_id={self.api_id}")
            self._shared_clients[key] = TelegramClient(StringSession(self.session), self.api_id, self.api_hash)
        return self._shared_clients[key]

    def list_new(self, state: Optional[Dict[str, Any]] = None) -> Iterator[SourceItem]:
        # Update local offset from state if provided
        if state:
            self.offset = state.get("offset", 0)

        last_id = self.offset
        client = self._client()

        # Connect if not connected
        if not client.is_connected():
             client.connect()

        try:
            # Resolve peer
            peer_entity = self.peer
            if isinstance(peer_entity, str) and peer_entity.startswith("-100"):
                try:
                    real_id, peer_type = utils.resolve_id(int(peer_entity))
                    peer_entity = peer_type(real_id)
                except Exception as e:
                    logger.warning(f"Failed to resolve marked ID {peer_entity}: {e}. Trying as is.")

            logger.info(f"Fetching messages from {self.peer} starting after ID {last_id}")

            # Iterate messages
            # min_id excludes the message with that ID, so we get newer ones
            for msg in client.iter_messages(peer_entity, min_id=last_id, reverse=True):
                self.offset = max(self.offset, msg.id)

                # 1. Text content
                text = msg.message or ""
                if text:
                     yield SourceItem(
                        external_id=str(msg.id),
                        data=text.encode("utf-8", errors="ignore"),
                        metadata={
                            "filename": f"msg_{msg.id}.txt",
                            "timestamp": msg.date.timestamp()
                        }
                    )

                # 2. Media content
                if msg.media:
                    try:
                        # Check size limit (20MB)
                        # Accessing msg.file returns a helper wrapper
                        f = msg.file
                        if f and f.size and f.size > 20 * 1024 * 1024:
                             logger.warning(f"Skipping media in msg {msg.id} (Size: {f.size})")
                             continue

                        data = client.download_media(msg, file=bytes)
                        if data:
                             # Try to get filename
                             filename = "unknown"
                             if f and f.name:
                                 filename = f.name
                             else:
                                 ext = ""
                                 if f and f.ext:
                                     ext = f.ext
                                 filename = f"media_{msg.id}{ext}"

                             yield SourceItem(
                                external_id=str(msg.id) + "_media",
                                data=data,
                                metadata={
                                    "filename": filename,
                                    "timestamp": msg.date.timestamp()
                                }
                            )
                    except Exception as e:
                        logger.error(f"Failed to download media for msg {msg.id}: {e}")

        except Exception as e:
            logger.error(f"Error listing new messages for {self.peer}: {e}")
            raise

    def get_state(self) -> Dict[str, Any]:
        return {"offset": self.offset}
