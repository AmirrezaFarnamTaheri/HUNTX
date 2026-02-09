import logging
import time
import threading
from dataclasses import dataclass
from typing import Dict, Any, Optional, Iterator, List
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon import utils
from telethon.tl.types import InputMessagesFilterDocument

logger = logging.getLogger(__name__)

# Media types to drop entirely (not useful for proxy configs)
_UNWANTED_MEDIA_ATTRS = ("photo", "video", "gif", "sticker", "voice", "audio", "video_note")

# How many text messages to accumulate before yielding a batch
_TEXT_BATCH_SIZE = 100


@dataclass
class SourceItem:
    __slots__ = ("external_id", "data", "metadata")
    external_id: str
    data: bytes
    metadata: Dict[str, Any]


class TelegramUserConnector:
    _local = threading.local()

    def __init__(self, api_id: int, api_hash: str, session: str, peer: str,
                 state: Optional[Dict[str, Any]] = None, fetch_windows: Optional[Dict[str, Any]] = None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self.peer = peer  # "@channel" or "-100123..."
        self.offset = (state or {}).get("offset", 0)
        fw = fetch_windows or {}
        self._msg_fresh_s = fw.get("msg_fresh_hours", 2) * 3600
        self._file_fresh_s = fw.get("file_fresh_hours", 48) * 3600
        self._msg_sub_s = fw.get("msg_subsequent_hours", 0) * 3600
        self._file_sub_s = fw.get("file_subsequent_hours", 0) * 3600

    def _client(self) -> TelegramClient:
        if not hasattr(self._local, "clients"):
            self._local.clients = {}

        key = (self.api_id, self.session)
        if key not in self._local.clients:
            logger.info(f"Initializing new Telegram User Client for api_id={self.api_id}")
            self._local.clients[key] = TelegramClient(StringSession(self.session), self.api_id, self.api_hash)
        return self._local.clients[key]

    def _ensure_connected(self, client: TelegramClient):
        if not client.is_connected():
            logger.info("[MTProto] Connecting to Telegram...")
            try:
                client.connect()
                logger.info("[MTProto] Connected.")
            except Exception as e:
                logger.error(f"[MTProto] Connection failed: {e}")
                raise

    def _resolve_peer(self, peer_entity):
        if isinstance(peer_entity, str) and peer_entity.startswith("-100"):
            try:
                real_id, peer_type = utils.resolve_id(int(peer_entity))
                return peer_type(real_id)
            except Exception as e:
                logger.warning(f"[MTProto] Failed to resolve marked ID {peer_entity}: {e}. Using as-is.")
        return peer_entity

    # ------------------------------------------------------------------
    # Pass 1: Text messages (fast, no downloads, batched)
    # ------------------------------------------------------------------

    def _fetch_text_pass(self, client, peer_entity, last_id, cutoff_text, stats) -> Iterator[SourceItem]:
        """Scan all messages, yield only text content. Skip anything with documents
        (those are handled in pass 2). This is fast because no downloads happen."""
        pass_start = time.time()
        scanned = 0
        yielded = 0
        total_bytes = 0
        batch: List[SourceItem] = []

        logger.info(
            f"[MTProto] ── Pass 1: Text messages ──  peer={self.peer}  min_id={last_id}  "
            f"batch_size={_TEXT_BATCH_SIZE}"
        )

        for msg in client.iter_messages(peer_entity, min_id=last_id, reverse=True):
            self.offset = max(self.offset, msg.id)
            scanned += 1

            # Progress every 500 messages (text scan is fast)
            if scanned % 500 == 0:
                elapsed = time.time() - pass_start
                logger.info(
                    f"[MTProto] Pass 1: scanned={scanned}  yielded={yielded}  "
                    f"batches_flushed={yielded // _TEXT_BATCH_SIZE}  elapsed={elapsed:.1f}s"
                )

            # Drop unwanted media types
            has_unwanted = any(getattr(msg, attr, None) for attr in _UNWANTED_MEDIA_ATTRS)
            if has_unwanted:
                stats["skipped_media_type"] += 1
                continue

            # Skip documents entirely in this pass (handled in pass 2)
            has_document = bool(msg.document)

            # Apply text cutoff
            if cutoff_text > 0 and msg.date.timestamp() < cutoff_text:
                if not has_document:
                    stats["skipped_cutoff"] += 1
                continue

            # Extract text content
            text = msg.message or ""
            if not text:
                if not has_document:
                    stats["skipped_no_content"] += 1
                continue

            # Skip if this is a document-only message (text from doc messages
            # is also captured here as a separate item, which is fine)
            stats["text_messages"] += 1
            text_bytes = text.encode("utf-8", errors="ignore")
            total_bytes += len(text_bytes)
            yielded += 1

            item = SourceItem(
                external_id=str(msg.id),
                data=text_bytes,
                metadata={
                    "filename": f"msg_{msg.id}.txt",
                    "timestamp": msg.date.timestamp(),
                    "is_text": True,
                },
            )
            batch.append(item)

            # Flush batch
            if len(batch) >= _TEXT_BATCH_SIZE:
                logger.info(
                    f"[MTProto] Pass 1: flushing batch of {len(batch)} text items  "
                    f"(total yielded={yielded})"
                )
                yield from batch
                batch.clear()

        # Flush remaining
        if batch:
            logger.info(
                f"[MTProto] Pass 1: flushing final batch of {len(batch)} text items"
            )
            yield from batch
            batch.clear()

        pass_dur = time.time() - pass_start
        rate = scanned / pass_dur if pass_dur > 0 else 0
        logger.info(
            f"[MTProto] ── Pass 1 done ──  scanned={scanned}  yielded={yielded}  "
            f"bytes={total_bytes / 1024:.1f} KB  duration={pass_dur:.2f}s  rate={rate:.0f} msg/s"
        )
        stats["_text_scanned"] = scanned
        stats["_text_bytes"] = total_bytes

    # ------------------------------------------------------------------
    # Pass 2: Document messages (slow, downloads, one-by-one)
    # ------------------------------------------------------------------

    def _fetch_document_pass(self, client, peer_entity, last_id, cutoff_file, stats) -> Iterator[SourceItem]:
        """Use Telegram's server-side InputMessagesFilterDocument to iterate
        only over messages that contain documents. Downloads happen here."""
        pass_start = time.time()
        scanned = 0
        yielded = 0
        total_bytes = 0

        logger.info(
            f"[MTProto] ── Pass 2: Documents (server-filtered) ──  peer={self.peer}  min_id={last_id}"
        )

        for msg in client.iter_messages(
            peer_entity, min_id=last_id, reverse=True,
            filter=InputMessagesFilterDocument,
        ):
            self.offset = max(self.offset, msg.id)
            scanned += 1

            # Progress every 50 documents (downloads are slow)
            if scanned % 50 == 0:
                elapsed = time.time() - pass_start
                logger.info(
                    f"[MTProto] Pass 2: scanned={scanned}  yielded={yielded}  "
                    f"bytes={total_bytes / 1024:.1f} KB  elapsed={elapsed:.1f}s"
                )

            # Apply file cutoff
            if cutoff_file > 0 and msg.date.timestamp() < cutoff_file:
                stats["skipped_cutoff"] += 1
                continue

            if not msg.document:
                continue

            try:
                f = msg.file

                # APK skip
                if f:
                    is_apk = False
                    if f.name and f.name.lower().endswith(".apk"):
                        is_apk = True
                    elif f.ext and f.ext.lower() == ".apk":
                        is_apk = True
                    if is_apk:
                        logger.debug(f"[MTProto] Skipping APK in msg {msg.id}: {f.name or '?'}")
                        stats["skipped_apk"] += 1
                        continue

                # Size limit (25 MB)
                if f and f.size and f.size > 25 * 1024 * 1024:
                    size_mb = f.size / (1024 * 1024)
                    logger.info(f"[MTProto] Skipping oversized file msg {msg.id} ({size_mb:.1f} MB)")
                    stats["skipped_size_limit"] += 1
                    continue

                data = client.download_media(msg, file=bytes)
                if data:
                    filename = "unknown"
                    if f and f.name:
                        filename = f.name
                    else:
                        ext = ""
                        if f and f.ext:
                            ext = f.ext
                        filename = f"media_{msg.id}{ext}"

                    total_bytes += len(data)
                    stats["media_messages"] += 1
                    yielded += 1

                    yield SourceItem(
                        external_id=str(msg.id) + "_media",
                        data=data,
                        metadata={"filename": filename, "timestamp": msg.date.timestamp()},
                    )
            except Exception as e:
                logger.error(f"[MTProto] Download failed msg {msg.id}: {e}")
                stats["download_errors"] += 1

        pass_dur = time.time() - pass_start
        rate = scanned / pass_dur if pass_dur > 0 else 0
        logger.info(
            f"[MTProto] ── Pass 2 done ──  scanned={scanned}  yielded={yielded}  "
            f"bytes={total_bytes / 1024:.1f} KB  duration={pass_dur:.2f}s  rate={rate:.0f} doc/s"
        )
        stats["_doc_scanned"] = scanned
        stats["_doc_bytes"] = total_bytes

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def list_new(self, state: Optional[Dict[str, Any]] = None) -> Iterator[SourceItem]:
        if state:
            new_offset = state.get("offset", 0)
            if new_offset > self.offset:
                logger.info(f"[MTProto] Updating offset from state: {self.offset} -> {new_offset}")
                self.offset = new_offset

        last_id = self.offset
        client = self._client()
        is_fresh_start = last_id == 0

        self._ensure_connected(client)

        try:
            peer_entity = self._resolve_peer(self.peer)

            mode = "fresh_start" if is_fresh_start else "subsequent"
            logger.info(
                f"[MTProto] ═══ Fetching {self.peer} ═══  min_id={last_id}  mode={mode}  "
                f"text_batch={_TEXT_BATCH_SIZE}\n"
                f"[MTProto]   cutoffs: msg_fresh={self._msg_fresh_s/3600:.0f}h  "
                f"file_fresh={self._file_fresh_s/3600:.0f}h  "
                f"msg_sub={self._msg_sub_s/3600:.0f}h  file_sub={self._file_sub_s/3600:.0f}h"
            )

            stats = {
                "text_messages": 0,
                "media_messages": 0,
                "skipped_size_limit": 0,
                "skipped_apk": 0,
                "skipped_no_content": 0,
                "skipped_media_type": 0,
                "skipped_cutoff": 0,
                "download_errors": 0,
                "_text_scanned": 0,
                "_text_bytes": 0,
                "_doc_scanned": 0,
                "_doc_bytes": 0,
            }

            # Compute cutoffs
            now = time.time()
            if is_fresh_start:
                cutoff_file = now - self._file_fresh_s if self._file_fresh_s > 0 else 0
                cutoff_text = now - self._msg_fresh_s if self._msg_fresh_s > 0 else 0
            else:
                cutoff_file = now - self._file_sub_s if self._file_sub_s > 0 else 0
                cutoff_text = now - self._msg_sub_s if self._msg_sub_s > 0 else 0

            overall_start = time.time()

            # Pass 1: text (fast, batched in groups of 100)
            yield from self._fetch_text_pass(client, peer_entity, last_id, cutoff_text, stats)

            # Pass 2: documents (server-filtered, one-by-one with downloads)
            yield from self._fetch_document_pass(client, peer_entity, last_id, cutoff_file, stats)

            overall_dur = time.time() - overall_start
            total_yielded = stats["text_messages"] + stats["media_messages"]
            total_bytes = stats["_text_bytes"] + stats["_doc_bytes"]

            logger.info(
                f"[MTProto] ═══ Done {self.peer} ═══  "
                f"yielded={total_yielded} (text={stats['text_messages']} docs={stats['media_messages']})  "
                f"total_bytes={total_bytes / 1024:.1f} KB  duration={overall_dur:.2f}s\n"
                f"[MTProto]   pass1_scanned={stats['_text_scanned']}  pass2_scanned={stats['_doc_scanned']}\n"
                f"[MTProto]   skipped: media_type={stats['skipped_media_type']}  cutoff={stats['skipped_cutoff']}  "
                f"no_content={stats['skipped_no_content']}  apk={stats['skipped_apk']}  "
                f"size_limit={stats['skipped_size_limit']}  dl_errors={stats['download_errors']}"
            )

            if total_yielded == 0 and is_fresh_start:
                logger.warning(
                    f"[MTProto] Zero items from {self.peer} on fresh start. "
                    f"Verify access and channel content."
                )

        except Exception as e:
            logger.error(f"[MTProto] Error listing messages for {self.peer}: {e}")
            raise

    def get_state(self) -> Dict[str, Any]:
        return {"offset": self.offset}

    def cleanup(self):
        """Clean up Telegram client connections to prevent asyncio errors."""
        if hasattr(self._local, "clients"):
            logger.info("[MTProto] Cleaning up client connections...")
            for key, client in self._local.clients.items():
                try:
                    if client.is_connected():
                        client.disconnect()
                        logger.debug(f"Disconnected Telegram client for key {key}")
                except Exception as e:
                    logger.warning(f"Error disconnecting Telegram client for key {key}: {e}")
            self._local.clients.clear()

    def __del__(self):
        """Ensure cleanup on object destruction."""
        try:
            self.cleanup()
        except Exception:
            pass
