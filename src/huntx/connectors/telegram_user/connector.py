import asyncio
import logging
import time
import threading
from dataclasses import dataclass
from typing import Dict, Any, Optional, AsyncIterator, List

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon import utils
    from telethon.tl.types import InputMessagesFilterDocument
    from telethon.errors import FloodWaitError
except ModuleNotFoundError:  # pragma: no cover
    TelegramClient = None  # type: ignore[assignment]
    StringSession = None  # type: ignore[assignment]
    InputMessagesFilterDocument = object()  # type: ignore[assignment]
    FloodWaitError = Exception

    class _UtilsStub:
        @staticmethod
        def resolve_id(_peer_id: int):
            raise RuntimeError("Telethon not installed")

    utils = _UtilsStub()  # type: ignore[assignment]

from ..base import SourceConnector, AsyncSyncIterator, async_iter, maybe_await, run_sync

logger = logging.getLogger(__name__)

# Media types to drop entirely (not useful for proxy configs)
_UNWANTED_MEDIA_ATTRS = ("photo", "video", "gif", "sticker", "voice", "audio", "video_note")

# How many text messages to accumulate before yielding a batch
_TEXT_BATCH_SIZE = 100

# Max reconnect retries per pass when connection drops
_MAX_RECONNECT_RETRIES = 10
_RECONNECT_DELAYS = (2, 2, 4, 4, 8, 8, 16, 16, 32, 32)  # seconds per retry attempt
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_DOWNLOAD_REQUEST_BYTES = 64 * 1024
_MAX_FLOOD_WAIT_SECONDS = 300


async def download_media_bounded(client: Any, media: Any) -> Optional[bytes]:
    """Stream MTProto media while enforcing the cap during transfer."""
    data = bytearray()
    stream = client.iter_download(media, request_size=_DOWNLOAD_REQUEST_BYTES)
    try:
        async for chunk in async_iter(stream):
            chunk_bytes = bytes(chunk)
            if len(data) + len(chunk_bytes) > MAX_DOWNLOAD_BYTES:
                return None
            data.extend(chunk_bytes)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            await maybe_await(close())
    return bytes(data) if data else None


@dataclass
class TelegramUserItem:
    __slots__ = ("external_id", "data", "metadata")
    external_id: str
    data: bytes
    metadata: Dict[str, Any]


class TelegramUserConnector(SourceConnector):
    _local = threading.local()
    _session_locks: Dict[str, threading.RLock] = {}
    _session_locks_lock = threading.Lock()
    _sync_lock: Optional[Any]
    _async_lock: Optional[asyncio.Lock]

    _session_locks_async: Dict[str, asyncio.Lock] = {}
    _session_locks_async_lock = threading.Lock()

    def _get_session_lock(self) -> threading.RLock:
        with self._session_locks_lock:
            if self.session not in self._session_locks:
                self._session_locks[self.session] = threading.RLock()
            return self._session_locks[self.session]

    def _get_session_lock_async(self) -> asyncio.Lock:
        with self._session_locks_async_lock:
            if self.session not in self._session_locks_async:
                self._session_locks_async[self.session] = asyncio.Lock()
            return self._session_locks_async[self.session]

    def __enter__(self):
        if self._sync_lock is None:
            lock = self._get_session_lock()
            lock.acquire()
            self._sync_lock = lock
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    async def __aenter__(self):
        if self._async_lock is None:
            lock = self._get_session_lock_async()
            await lock.acquire()
            self._async_lock = lock
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup_async()

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session: str,
        peer: str,
        state: Optional[Dict[str, Any]] = None,
        fetch_windows: Optional[Dict[str, Any]] = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self.peer = peer  # "@channel" or "-100123..."
        initial_state = state or {}
        legacy_offset = initial_state.get("offset", 0)
        self._text_offset = initial_state.get("text_offset", legacy_offset)
        self._document_offset = initial_state.get(
            "document_offset",
            legacy_offset,
        )
        self._text_scanned_offset = self._text_offset
        self._document_scanned_offset = self._document_offset
        self._text_pending: set[int] = set()
        self._document_pending: set[int] = set()
        self.offset = min(self._text_offset, self._document_offset)
        self._client_key = (self.api_id, self.session)
        self._sync_lock = None
        self._async_lock = None
        fw = fetch_windows or {}
        self._msg_fresh_s = fw.get("msg_fresh_hours", 2) * 3600
        self._file_fresh_s = fw.get("file_fresh_hours", 48) * 3600
        self._msg_sub_s = fw.get("msg_subsequent_hours", 0) * 3600
        self._file_sub_s = fw.get("file_subsequent_hours", 0) * 3600
        self.deadline: Optional[float] = None

    def _refresh_committed_offsets(self) -> None:
        text_limit = min(self._text_pending) - 1 if self._text_pending else self._text_scanned_offset
        document_limit = min(self._document_pending) - 1 if self._document_pending else self._document_scanned_offset
        self._text_offset = max(self._text_offset, text_limit)
        self._document_offset = max(
            self._document_offset,
            document_limit,
        )
        self.offset = min(self._text_offset, self._document_offset)

    def _client(self) -> TelegramClient:
        # Allow tests to inject a mock client even if Telethon isn't installed.
        if hasattr(self._local, "clients") and getattr(self._local, "clients"):
            if self._client_key in self._local.clients:
                return self._local.clients[self._client_key]

        if TelegramClient is None or StringSession is None:
            raise RuntimeError(
                "Telethon is required for telegram_user sources. Install dependencies (pip install -e .)."
            )
        if not hasattr(self._local, "clients"):
            self._local.clients = {}

        if self._client_key not in self._local.clients:
            logger.info(f"Initializing new Telegram User Client for api_id={self.api_id}")
            if self._sync_lock is None and self._async_lock is None:
                lock = self._get_session_lock()
                lock.acquire()
                self._sync_lock = lock
            try:
                self._local.clients[self._client_key] = TelegramClient(
                    StringSession(self.session),
                    self.api_id,
                    self.api_hash,
                )
            except Exception:
                self._release_sync_lock()
                raise
        return self._local.clients[self._client_key]

    def _ensure_connected(self, client: TelegramClient):
        run_sync(self._ensure_connected_async(client))

    async def _ensure_connected_async(self, client: TelegramClient):
        if not client.is_connected():
            logger.info("[MTProto] Connecting to Telegram...")
            try:
                await maybe_await(client.connect())
                logger.info("[MTProto] Connected.")
            except Exception as e:
                logger.error(f"[MTProto] Connection failed: {e}")
                raise

    def _resolve_peer(self, peer_entity, client: TelegramClient = None):
        return run_sync(self._resolve_peer_async(peer_entity, client))

    async def _resolve_peer_async(self, peer_entity, client: TelegramClient = None):
        if client and isinstance(peer_entity, str) and peer_entity.startswith("-100"):
            try:
                entity = await maybe_await(client.get_entity(int(peer_entity)))
                logger.debug(f"[MTProto] Resolved {peer_entity} via API -> {type(entity).__name__}")
                return entity
            except Exception as e:
                logger.warning(
                    f"[MTProto] API resolution failed for {peer_entity}: {e}. " f"Falling back to raw PeerChannel."
                )
                try:
                    real_id, peer_type = utils.resolve_id(int(peer_entity))  # type: ignore[union-attr]
                    return peer_type(real_id)
                except Exception as e2:
                    logger.warning(f"[MTProto] Fallback also failed for {peer_entity}: {e2}. Using as-is.")
        elif isinstance(peer_entity, str) and peer_entity.startswith("-100"):
            try:
                real_id, peer_type = utils.resolve_id(int(peer_entity))  # type: ignore[union-attr]
                return peer_type(real_id)
            except Exception as e:
                logger.warning(f"[MTProto] Failed to resolve marked ID {peer_entity}: {e}. Using as-is.")
        return peer_entity

    def resolve_channel_id(self) -> Optional[int]:
        return run_sync(self.resolve_channel_id_async())

    async def resolve_channel_id_async(self) -> Optional[int]:
        client = self._client()
        await self._ensure_connected_async(client)
        try:
            entity = await maybe_await(
                client.get_entity(int(self.peer) if self.peer.lstrip("-").isdigit() else self.peer)
            )
            raw_id = getattr(entity, "id", None)
            if raw_id:
                logger.info(f"[MTProto] Resolved peer {self.peer} -> channel_id={raw_id}")
            return raw_id
        except Exception as e:
            logger.warning(f"[MTProto] Could not resolve peer {self.peer} for dedup: {e}")
            return None

    # ------------------------------------------------------------------
    # Pass 1: Text messages (fast, no downloads, batched)
    # ------------------------------------------------------------------

    async def _reconnect_async(self, client, retry_num: int):
        """Reconnect a dropped Telethon client with stepped backoff."""
        delay = _RECONNECT_DELAYS[min(retry_num, len(_RECONNECT_DELAYS) - 1)]
        logger.warning(
            f"[MTProto] Connection lost. Reconnecting in {delay}s "
            f"(attempt {retry_num + 1}/{_MAX_RECONNECT_RETRIES})..."
        )
        await asyncio.sleep(delay)
        try:
            if client.is_connected():
                await maybe_await(client.disconnect())
        except Exception as e:
            logger.debug(f"[MTProto] Disconnect failed during reconnect: {e}")
        await maybe_await(client.connect())
        logger.info("[MTProto] Reconnected.")

    async def _fetch_text_pass(
        self, client, peer_entity, last_id, cutoff_text, stats
    ) -> AsyncIterator[TelegramUserItem]:
        """Scan all messages, yield only text content. Skip anything with documents."""
        pass_start = time.time()
        scanned = 0
        yielded = 0
        total_bytes = 0
        batch: List[TelegramUserItem] = []
        resume_after_id = last_id

        logger.info(
            f"[MTProto] ── Pass 1: Text messages ──  peer={self.peer}  min_id={last_id}  "
            f"batch_size={_TEXT_BATCH_SIZE}"
        )

        retries = 0
        while retries <= _MAX_RECONNECT_RETRIES:
            try:
                async for msg in async_iter(client.iter_messages(peer_entity, min_id=resume_after_id, reverse=True)):
                    if getattr(self, "deadline", None) and self.deadline is not None and time.time() > self.deadline:
                        logger.warning("[MTProto] Ingestion deadline exceeded during text pass. Aborting.")
                        break
                    resume_after_id = max(resume_after_id, msg.id)
                    self._text_scanned_offset = max(
                        self._text_scanned_offset,
                        msg.id,
                    )
                    scanned += 1

                    # Progress every 500 messages
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

                    # Skip documents entirely in this pass
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

                    stats["text_messages"] += 1
                    text_bytes = text.encode("utf-8", errors="ignore")
                    total_bytes += len(text_bytes)
                    yielded += 1

                    item = TelegramUserItem(
                        external_id=str(msg.id),
                        data=text_bytes,
                        metadata={
                            "filename": f"msg_{msg.id}.txt",
                            "timestamp": msg.date.timestamp(),
                            "is_text": True,
                            "_cursor_kind": "text",
                            "_cursor_id": msg.id,
                        },
                    )
                    self._text_pending.add(msg.id)
                    batch.append(item)

                    # Flush batch
                    if len(batch) >= _TEXT_BATCH_SIZE:
                        logger.info(
                            f"[MTProto] Pass 1: flushing batch of {len(batch)} text items  "
                            f"(total yielded={yielded})"
                        )
                        for b_item in batch:
                            yield b_item
                        batch.clear()

                break

            except FloodWaitError as e:
                wait_seconds = int(e.seconds)
                if wait_seconds > _MAX_FLOOD_WAIT_SECONDS:
                    raise RuntimeError(
                        f"Telegram FloodWait {wait_seconds}s exceeds " f"{_MAX_FLOOD_WAIT_SECONDS}s safety bound"
                    ) from e
                logger.warning(f"[MTProto] FloodWait for {wait_seconds}s. Sleeping...")
                await asyncio.sleep(wait_seconds)
                continue
            except ConnectionError as e:
                retries += 1
                if retries > _MAX_RECONNECT_RETRIES:
                    logger.error(f"[MTProto] Pass 1: exhausted {_MAX_RECONNECT_RETRIES} reconnect retries: {e}")
                    raise
                await self._reconnect_async(client, retries - 1)
                logger.info(f"[MTProto] Pass 1: resuming from min_id={resume_after_id} after reconnect")

        # Flush remaining
        if batch:
            logger.info(f"[MTProto] Pass 1: flushing final batch of {len(batch)} text items")
            for b_item in batch:
                yield b_item
            batch.clear()

        pass_dur = time.time() - pass_start
        rate = scanned / pass_dur if pass_dur > 0 else 0
        logger.info(
            f"[MTProto] ── Pass 1 done ──  scanned={scanned}  yielded={yielded}  "
            f"bytes={total_bytes / 1024:.1f} KB  duration={pass_dur:.2f}s  rate={rate:.0f} msg/s"
        )
        self._refresh_committed_offsets()
        stats["_text_scanned"] = scanned
        stats["_text_bytes"] = total_bytes

    # ------------------------------------------------------------------
    # Pass 2: Document messages (slow, downloads, one-by-one)
    # ------------------------------------------------------------------

    async def _fetch_document_pass(
        self, client, peer_entity, last_id, cutoff_file, stats
    ) -> AsyncIterator[TelegramUserItem]:
        """Use Telegram's server-side InputMessagesFilterDocument to iterate only over documents."""
        pass_start = time.time()
        scanned = 0
        yielded = 0
        total_bytes = 0
        resume_after_id = last_id

        logger.info(f"[MTProto] ── Pass 2: Documents (server-filtered) ──  peer={self.peer}  min_id={last_id}")

        retries = 0
        while retries <= _MAX_RECONNECT_RETRIES:
            try:
                async for msg in async_iter(
                    client.iter_messages(
                        peer_entity,
                        min_id=resume_after_id,
                        reverse=True,
                        filter=InputMessagesFilterDocument,
                    )
                ):

                    if getattr(self, "deadline", None) and self.deadline is not None and time.time() > self.deadline:
                        logger.warning("[MTProto] Ingestion deadline exceeded during document pass. Aborting.")
                        break
                    resume_after_id = max(resume_after_id, msg.id)
                    self._document_scanned_offset = max(
                        self._document_scanned_offset,
                        msg.id,
                    )
                    scanned += 1

                    # Progress every 50 documents
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
                        if f and f.size and f.size > MAX_DOWNLOAD_BYTES:
                            size_mb = f.size / (1024 * 1024)
                            logger.info(f"[MTProto] Skipping oversized file msg {msg.id} ({size_mb:.1f} MB)")
                            stats["skipped_size_limit"] += 1
                            continue

                        data = await download_media_bounded(client, msg)
                        if data is None:
                            logger.warning(
                                f"[MTProto] Discarding msg {msg.id}: download " "was empty or exceeded the 25MB cap"
                            )
                            stats["skipped_size_limit"] += 1
                            continue
                        if data:
                            from ...utils.content_type import is_executable

                            is_exec, type_desc = is_executable(data)
                            if is_exec:
                                logger.info(
                                    f"[MTProto] Skipping executable in msg {msg.id}: {f.name or '?'} ({type_desc})"
                                )
                                stats["skipped_apk"] += 1
                                continue

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

                            self._document_pending.add(msg.id)
                            yield TelegramUserItem(
                                external_id=str(msg.id) + "_media",
                                data=data,
                                metadata={
                                    "filename": filename,
                                    "timestamp": msg.date.timestamp(),
                                    "_cursor_kind": "document",
                                    "_cursor_id": msg.id,
                                },
                            )
                    except ConnectionError:
                        raise
                    except Exception as e:
                        self._document_pending.add(msg.id)
                        logger.error(f"[MTProto] Download failed msg {msg.id}: {e}")
                        stats["download_errors"] += 1
                        raise

                break

            except FloodWaitError as e:
                wait_seconds = int(e.seconds)
                if wait_seconds > _MAX_FLOOD_WAIT_SECONDS:
                    raise RuntimeError(
                        f"Telegram FloodWait {wait_seconds}s exceeds " f"{_MAX_FLOOD_WAIT_SECONDS}s safety bound"
                    ) from e
                logger.warning(f"[MTProto] FloodWait for {wait_seconds}s. Sleeping...")
                await asyncio.sleep(wait_seconds)
                continue
            except ConnectionError as e:
                retries += 1
                if retries > _MAX_RECONNECT_RETRIES:
                    logger.error(f"[MTProto] Pass 2: exhausted {_MAX_RECONNECT_RETRIES} reconnect retries: {e}")
                    raise
                await self._reconnect_async(client, retries - 1)
                logger.info(f"[MTProto] Pass 2: resuming from min_id={resume_after_id} after reconnect")

        pass_dur = time.time() - pass_start
        rate = scanned / pass_dur if pass_dur > 0 else 0
        logger.info(
            f"[MTProto] ── Pass 2 done ──  scanned={scanned}  yielded={yielded}  "
            f"bytes={total_bytes / 1024:.1f} KB  duration={pass_dur:.2f}s  rate={rate:.0f} doc/s"
        )
        self._refresh_committed_offsets()
        stats["_doc_scanned"] = scanned
        stats["_doc_bytes"] = total_bytes

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def list_new(self, state: Optional[Dict[str, Any]] = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: Optional[Dict[str, Any]] = None):
        if state:
            legacy_offset = state.get("offset", 0)
            self._text_offset = max(
                self._text_offset,
                state.get("text_offset", legacy_offset),
            )
            self._document_offset = max(
                self._document_offset,
                state.get("document_offset", legacy_offset),
            )
            self.offset = min(
                self._text_offset,
                self._document_offset,
            )

        text_last_id = self._text_offset
        document_last_id = self._document_offset
        last_id = min(text_last_id, document_last_id)
        client = self._client()
        is_fresh_start = last_id == 0

        await self._ensure_connected_async(client)

        try:
            peer_entity = await self._resolve_peer_async(self.peer, client)

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
            async for item in self._fetch_text_pass(
                client,
                peer_entity,
                text_last_id,
                cutoff_text,
                stats,
            ):
                yield item

            # Pass 2: documents (server-filtered, one-by-one with downloads)
            async for item in self._fetch_document_pass(
                client,
                peer_entity,
                document_last_id,
                cutoff_file,
                stats,
            ):
                yield item

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
                    f"[MTProto] Zero items from {self.peer} on fresh start. " f"Verify access and channel content."
                )

        except Exception as e:
            logger.error(f"[MTProto] Error listing messages for {self.peer}: {e}")
            raise

    def acknowledge(self, items) -> None:
        """Advance only cursors whose yielded bytes are durably recorded."""
        for item in items:
            metadata = getattr(item, "metadata", {})
            cursor_id = metadata.get("_cursor_id")
            cursor_kind = metadata.get("_cursor_kind")
            if not isinstance(cursor_id, int):
                continue
            if cursor_kind == "text":
                self._text_scanned_offset = max(
                    self._text_scanned_offset,
                    cursor_id,
                )
                self._text_pending.discard(cursor_id)
            elif cursor_kind == "document":
                self._document_scanned_offset = max(
                    self._document_scanned_offset,
                    cursor_id,
                )
                self._document_pending.discard(cursor_id)
        self._refresh_committed_offsets()

    def get_state(self) -> Dict[str, Any]:
        self._refresh_committed_offsets()
        return {
            "offset": min(self._text_offset, self._document_offset),
            "text_offset": self._text_offset,
            "document_offset": self._document_offset,
        }

    def cleanup(self):
        """Clean up Telegram client connections synchronously."""
        clients = getattr(self._local, "clients", {})
        client = clients.get(self._client_key)
        try:
            if client is not None and client.is_connected():
                client.disconnect()
                logger.debug("Disconnected owned Telegram client for key %s", self._client_key)
        except Exception as exc:
            logger.warning("Error disconnecting Telegram client for key %s: %s", self._client_key, exc)
        finally:
            clients.pop(self._client_key, None)
            self._release_sync_lock()

    async def cleanup_async(self):
        """Clean up Telegram client connections asynchronously."""
        clients = getattr(self._local, "clients", {})
        client = clients.get(self._client_key)
        try:
            if client is not None and client.is_connected():
                await maybe_await(client.disconnect())
                logger.debug("Disconnected owned Telegram client for key %s", self._client_key)
        except RuntimeError as exc:
            if "Event loop is closed" in str(exc):
                logger.debug("Expected loop closure during cleanup for %s: %s", self._client_key, exc)
            else:
                logger.warning("RuntimeError disconnecting Telegram client for %s: %s", self._client_key, exc)
        except Exception as exc:
            logger.warning("Error disconnecting Telegram client for key %s: %s", self._client_key, exc)
        finally:
            clients.pop(self._client_key, None)
            self._release_async_lock()

    def _release_sync_lock(self) -> None:
        lock, self._sync_lock = self._sync_lock, None
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass

    def _release_async_lock(self) -> None:
        lock, self._async_lock = self._async_lock, None
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass

    def _release_session_locks(self) -> None:
        """Release any held session lock without performing I/O."""
        self._release_sync_lock()
        self._release_async_lock()

    def __del__(self):
        """Release the in-process session lock on destruction.

        Deliberately does NOT disconnect clients. ``__del__`` runs at
        arbitrary GC time and during interpreter shutdown, where the event
        loop may be closed or absent and module globals may already be torn
        down to ``None``; driving Telethon's network disconnect from here is
        unreliable and can raise or hang (exceptions in ``__del__`` are
        swallowed and merely printed to stderr, so failures are invisible).

        The session lock is a pure in-process resource that would otherwise
        leak and deadlock later acquisitions, so releasing it is both safe
        and necessary. Socket teardown is left to the explicit
        ``cleanup()`` / ``cleanup_async()`` paths (the latter used by the
        async context manager), with the OS reclaiming any socket whose
        client object is garbage-collected.
        """
        try:
            self._release_session_locks()
        except Exception:
            # Never raise from __del__; there is no caller to handle it and
            # logging may itself be unavailable during interpreter shutdown.
            pass
