import logging
import json
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
            new_offset = state.get("offset", 0)
            if new_offset > self.offset:
                logger.info(f"Updating offset from state: {self.offset} -> {new_offset}")
                self.offset = new_offset

        last_id = self.offset
        client = self._client()
        is_fresh_start = (last_id == 0)

        # Connect if not connected
        if not client.is_connected():
             logger.info(f"Connecting to Telegram MTProto...")
             try:
                 client.connect()
                 logger.info(f"Connected to Telegram MTProto.")
             except Exception as e:
                 logger.error(f"Failed to connect to Telegram MTProto: {e}")
                 raise

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

            count = 0
            stats = {
                "text_messages": 0,
                "media_messages": 0,
                "skipped_size_limit": 0,
                "skipped_apk": 0,
                "skipped_no_content": 0,
                "download_errors": 0
            }

            # Iterate messages
            # min_id excludes the message with that ID, so we get newer ones
            for msg in client.iter_messages(peer_entity, min_id=last_id, reverse=True):
                self.offset = max(self.offset, msg.id)
                count += 1

                # logger.debug(f"Processing message {msg.id} (Date: {msg.date})")

                content_found = False

                # 1. Text content
                text = msg.message or ""
                if text:
                     logger.info(f"Message {msg.id} has text content. Yielding.")
                     stats["text_messages"] += 1
                     content_found = True
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

                        # APK Skip Logic
                        if f:
                            is_apk = False
                            if f.name and f.name.lower().endswith(".apk"):
                                is_apk = True
                            elif f.ext and f.ext.lower() == ".apk":
                                is_apk = True

                            if is_apk:
                                logger.info(f"Skipping APK media in msg {msg.id}: {f.name or 'unknown'}")
                                stats["skipped_apk"] += 1
                                continue

                        if f and f.size and f.size > 20 * 1024 * 1024:
                             size_mb = f.size / (1024 * 1024)
                             logger.warning(f"Skipping media in msg {msg.id} (Size: {size_mb:.2f}MB > 20MB)")
                             stats["skipped_size_limit"] += 1
                             continue

                        logger.debug(f"Downloading media for msg {msg.id}...")
                        data = client.download_media(msg, file=bytes)
                        if data:
                             content_found = True
                             # Try to get filename
                             filename = "unknown"
                             if f and f.name:
                                 filename = f.name
                             else:
                                 ext = ""
                                 if f and f.ext:
                                     ext = f.ext
                                 filename = f"media_{msg.id}{ext}"

                             size_kb = len(data) / 1024
                             logger.info(f"Downloaded media {filename} from msg {msg.id} (Size: {size_kb:.2f}KB)")
                             stats["media_messages"] += 1

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
                        stats["download_errors"] += 1

                if not content_found:
                    # logger.debug(f"Message {msg.id} has no text or valid media. Skipping.")
                    stats["skipped_no_content"] += 1

            logger.info(f"Finished fetching messages from {self.peer}. Processed {count} messages. Stats: {json.dumps(stats)}")

            if count == 0 and is_fresh_start:
                 logger.warning(f"Fetched 0 messages from {self.peer} on a fresh start. "
                                f"Ensure the user/bot has access to the channel and the channel is not empty.")

        except Exception as e:
            logger.error(f"Error listing new messages for {self.peer}: {e}")
            raise

    def get_state(self) -> Dict[str, Any]:
        return {"offset": self.offset}
