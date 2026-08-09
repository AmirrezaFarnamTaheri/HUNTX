import datetime
import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, List

from ..config.schema import normalize_destination_mode
from ..publishers.telegram.publisher import (
    TelegramPublisher,
    UnknownPublicationOutcome,
)
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
        data = bytes(data)
        actual_hash = hashlib.sha256(data).hexdigest()
        if new_hash != actual_hash:
            raise ValueError(f"Artifact digest does not match publication payload for {unique_id}")
        data_size_kb = len(data) / 1024

        if fmt in _ZIP_FORMATS and len(data) <= _EMPTY_ZIP_THRESHOLD:
            logger.debug("[Publish] Skipping minimal artifact %s (%s bytes)", unique_id, len(data))
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

        generation = str(build_result.get("generation") or new_hash)
        intent_id = self.state_repo.ensure_publication_intent(
            unique_id,
            new_hash,
            generation=generation,
        )
        published_any = False
        failures: List[str] = []
        destination_coordinates: list[str] = []
        confirmed_this_run: set[str] = set()
        stable_destination_ids: set[str] = set()
        logger.info(
            "[Publish] Content changed for %s hash=%s -> %s size=%.1f KB destinations=%s",
            unique_id,
            "LEDGER",
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
            if not isinstance(dest, dict):
                raise ValueError("Publish destination must be a mapping")
            chat_id = str(dest.get("chat_id") or "").strip()
            if not chat_id:
                raise ValueError("Publish destination requires chat_id")
            mode = normalize_destination_mode(dest.get("mode"))
            stable_id = str(dest.get("id") or f"{mode}:{chat_id}").strip()
            if stable_id in stable_destination_ids:
                raise ValueError(f"Duplicate destination identity: {stable_id}")
            stable_destination_ids.add(stable_id)
            template = dest.get("caption_template", "Update: {timestamp}")
            if not isinstance(template, str):
                raise ValueError(f"Caption template for {stable_id} must be a string")
            token = dest.get("token") or default_token
            required = dest.get("required", True)
            if not token:
                msg = f"No token configured for destination {stable_id}"
                if required:
                    if os.getenv("HUNTX_STRICT", "0").strip().lower() in {
                        "1",
                        "true",
                        "yes",
                    }:
                        raise RuntimeError(f"Strict Mode Active: {msg}")
                    raise RuntimeError(msg)
                logger.warning("[Publish] %s", msg)
                continue

            config_material = "\0".join(
                [
                    stable_id,
                    mode,
                    chat_id,
                    hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
                    template,
                    str(bool(required)),
                ]
            )
            destination_id = f"{stable_id}@" f"{hashlib.sha256(config_material.encode('utf-8')).hexdigest()[:16]}"
            destination_coordinates.append(destination_id)
            delivery_state = self.state_repo.get_delivery_state(
                intent_id,
                destination_id,
            )
            if delivery_state == "confirmed":
                logger.debug(
                    "[Publish] Destination already confirmed intent=%s destination=%s",
                    intent_id,
                    stable_id,
                )
                continue
            if delivery_state == "unknown_outcome":
                failures.append(f"destination={stable_id} error=UnknownPublicationOutcome")
                logger.error(
                    "[Publish] Refusing automatic resend to %s because the "
                    "previous outcome is unknown; reconcile the remote receipt "
                    "before retrying",
                    stable_id,
                )
                continue

            publisher, publisher_lock = self._publisher_for(token)
            try:
                caption = template.format(
                    timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    sha12=new_hash[:12],
                    count=build_result.get("count", "?"),
                    format=fmt,
                )
                started = time.monotonic()
                logger.info(
                    "[Publish] Publishing '%s' to destination %s",
                    filename,
                    stable_id,
                )
                self.state_repo.mark_delivery_sending(intent_id, destination_id)
                with publisher_lock:
                    receipt = publisher.publish(chat_id, data, filename, caption)
                self.state_repo.mark_delivery_confirmed(
                    intent_id,
                    destination_id,
                    remote_receipt=str(receipt) if receipt is not None else None,
                )
                confirmed_this_run.add(destination_id)
                published_any = True
                logger.info(
                    "[Publish] Successfully published to %s (%.2fs)",
                    chat_id,
                    time.monotonic() - started,
                )
            except Exception as exc:
                self.state_repo.mark_delivery_failed(
                    intent_id,
                    destination_id,
                    error_class=type(exc).__name__,
                    unknown_outcome=isinstance(
                        exc,
                        UnknownPublicationOutcome,
                    ),
                )
                msg = f"destination={stable_id} error={type(exc).__name__}"
                failures.append(msg)
                logger.error("[Publish] Failed to publish to %s", msg)

        all_confirmed = bool(destination_coordinates) and all(
            destination_id in confirmed_this_run or self.state_repo.is_delivery_confirmed(intent_id, destination_id)
            for destination_id in destination_coordinates
        )
        if all_confirmed:
            self.state_repo.complete_publication_intent(intent_id)
            self.state_repo.mark_published(unique_id, new_hash)
            logger.info("[Publish] Published %s (%s) successfully.", unique_id, new_hash)

        if failures:
            raise RuntimeError(
                f"Publish failed for {unique_id}: {len(failures)} destination error(s): " + "; ".join(failures)
            )

        if all_confirmed:
            return True

        logger.warning("[Publish] No destinations successfully published for %s", unique_id)
        return published_any
