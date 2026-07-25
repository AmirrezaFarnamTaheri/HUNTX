import datetime
import logging
import os
import threading
import time
from typing import Any, Dict, List

from ..publishers.telegram.publisher import TelegramPublisher
from ..state.repo import StateRepo
from ..utils.safe_names import safe_component

logger = logging.getLogger(__name__)

_ZIP_FORMATS = {"ovpn", "opaque_bundle", "ehi", "hc", "hat", "sip", "npv4", "nm", "dark"}
_EXT_MAPPING = {"conf_lines": ".conf", "npvt": ".txt", "npvtsub": ".txt"}
_EXT_LOOKUP = {**{fmt: ".zip" for fmt in _ZIP_FORMATS}, **_EXT_MAPPING}
_DEFAULT_EXT = ".txt"
_EMPTY_ZIP_THRESHOLD = 22


class PublishPipeline:
    def __init__(self, state_repo: StateRepo):
        self.state_repo = state_repo
        self.publishers: Dict[str, TelegramPublisher] = {}
        self._publisher_locks: Dict[str, threading.Lock] = {}
        self._publisher_guard = threading.Lock()
        self._hash_cache: Dict[str, str | None] = {}
        self._hash_guard = threading.Lock()

    def _publisher_for(self, token: str) -> tuple[TelegramPublisher, threading.Lock]:
        with self._publisher_guard:
            publisher = self.publishers.get(token)
            if publisher is None:
                publisher = TelegramPublisher(token)
                self.publishers[token] = publisher
            lock = self._publisher_locks.get(token)
            if lock is None:
                lock = threading.Lock()
                self._publisher_locks[token] = lock
            return publisher, lock

    def _last_published_hash(self, unique_id: str) -> str | None:
        with self._hash_guard:
            if unique_id in self._hash_cache:
                return self._hash_cache[unique_id]
        value = self.state_repo.get_last_published_hash(unique_id)
        with self._hash_guard:
            return self._hash_cache.setdefault(unique_id, value)

    def _remember_published_hash(self, unique_id: str, artifact_hash: str) -> None:
        with self._hash_guard:
            self._hash_cache[unique_id] = artifact_hash

    def run(self, build_result: Dict[str, Any], destinations: List[Dict[str, Any]]) -> bool:
        route_name = build_result["route_name"]
        new_hash = build_result["artifact_hash"]
        fmt = build_result.get("format", "unknown")
        unique_id = build_result.get("unique_id", route_name)
        data = build_result.get("data", b"")
        if not isinstance(data, (bytes, bytearray)):
            data = str(data).encode("utf-8")
        data_size_kb = len(data) / 1024

        if fmt in _ZIP_FORMATS and len(data) <= _EMPTY_ZIP_THRESHOLD:
            logger.debug("[Publish] Skipping minimal artifact %s (%s bytes)", unique_id, len(data))
            return True

        last_hash = self._last_published_hash(unique_id)
        if last_hash == new_hash:
            logger.debug(
                "[Publish] No change for %s (hash=%s), skip.",
                unique_id,
                last_hash[:12] if last_hash else "None",
            )
            return True

        if not destinations:
            raise RuntimeError(f"No publish destinations configured for {unique_id}")

        publish_bot_token = os.getenv("PUBLISH_BOT_TOKEN")
        ingest_token = os.getenv("TELEGRAM_TOKEN")
        default_token = publish_bot_token or ingest_token
        if not publish_bot_token and default_token and ingest_token and default_token == ingest_token:
            logger.warning(
                "WARNING (F-09): publish is using TELEGRAM_TOKEN because "
                "PUBLISH_BOT_TOKEN is unset; configure a distinct token to avoid conflicts."
            )

        published_any = False
        failures: List[str] = []
        logger.info(
            "[Publish] Content changed for %s hash=%s -> %s size=%.1f KB destinations=%s",
            unique_id,
            last_hash[:12] if last_hash else "NEW",
            new_hash[:12],
            data_size_kb,
            len(destinations),
        )

        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(fmt, default="fmt")
        ext = _EXT_LOOKUP.get(fmt, _DEFAULT_EXT)
        if ext == _DEFAULT_EXT:
            if fmt.endswith(".decoded.json"):
                ext = ".json"
            elif fmt.endswith(".b64sub"):
                ext = ".txt"
        filename = f"{safe_route}_{safe_fmt}_{new_hash[:8]}{ext}"

        for dest in destinations:
            chat_id = dest["chat_id"]
            template = dest.get("caption_template", "Update: {timestamp}")
            token = dest.get("token") or default_token
            if not token:
                msg = f"No token configured for destination chat_id={chat_id}. Skipping publish."
                strict = os.getenv("HUNTX_STRICT", "0") in ("1", "true", "TRUE")
                strict = strict or os.getenv("CI", "0") in ("1", "true", "TRUE")
                if strict:
                    raise RuntimeError(f"Strict Mode Active: {msg}")
                logger.warning("[Publish] %s", msg)
                continue

            masked_token = f"{token[:5]}...{token[-5:]}" if len(token) > 10 else "***"
            publisher, publisher_lock = self._publisher_for(token)
            caption = template.format(
                timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sha12=new_hash[:12],
                count=build_result.get("count", "?"),
                format=fmt,
            )

            try:
                started = time.monotonic()
                logger.info(
                    "[Publish] Publishing '%s' to chat %s (token %s)",
                    filename,
                    chat_id,
                    masked_token,
                )
                with publisher_lock:
                    publisher.publish(chat_id, data, filename, caption)
                published_any = True
                logger.info(
                    "[Publish] Successfully published to %s (%.2fs)",
                    chat_id,
                    time.monotonic() - started,
                )
            except Exception as exc:
                msg = f"chat_id={chat_id} error={exc}"
                failures.append(msg)
                logger.error("[Publish] Failed to publish to %s", msg)

        if failures:
            raise RuntimeError(
                f"Publish failed for {unique_id}: {len(failures)} destination error(s): " + "; ".join(failures)
            )

        if published_any:
            self.state_repo.mark_published(unique_id, new_hash)
            self._remember_published_hash(unique_id, new_hash)
            logger.info("[Publish] Published %s (%s) successfully.", unique_id, new_hash)
            return True

        logger.warning("[Publish] No destinations successfully published for %s", unique_id)
        return True
