import logging
import datetime
import os
import time
from typing import Dict, Any, List
from ..state.repo import StateRepo
from ..publishers.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)

_ZIP_FORMATS = ("ovpn", "opaque_bundle", "ehi", "hc", "hat", "sip", "npv4", "nm", "dark")

# An empty ZIP file (no entries) is exactly 22 bytes.
_EMPTY_ZIP_THRESHOLD = 22


class PublishPipeline:
    def __init__(self, state_repo: StateRepo):
        self.state_repo = state_repo
        self.publishers: Dict[str, TelegramPublisher] = {}

    def run(self, build_result: Dict[str, Any], destinations: List[Dict[str, Any]]):
        route_name = build_result["route_name"]
        new_hash = build_result["artifact_hash"]
        fmt = build_result.get("format", "unknown")
        unique_id = build_result.get("unique_id", route_name)
        data = build_result.get("data", b"")
        if not isinstance(data, (bytes, bytearray)):
            data = str(data).encode("utf-8")
        data_size_kb = len(data) / 1024

        # Skip empty/minimal ZIP artifacts (e.g. empty ZIPs).
        # Do not apply this to text formats because tiny payloads can be valid.
        if fmt in _ZIP_FORMATS and len(data) <= _EMPTY_ZIP_THRESHOLD:
            logger.debug(f"[Publish] Skipping minimal artifact {unique_id} ({len(data)} bytes)")
            return

        # Check if changed using unique_id (route + format)
        last_hash = self.state_repo.get_last_published_hash(unique_id)
        if last_hash == new_hash:
            logger.debug(f"[Publish] No change for {unique_id} (hash={last_hash[:12]}), skip.")
            return

        default_token = os.getenv("PUBLISH_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        published_any = False

        logger.info(
            f"[Publish] Content changed for {unique_id}  "
            f"hash={last_hash[:12] if last_hash else 'NEW'} → {new_hash[:12]}  "
            f"size={data_size_kb:.1f} KB  destinations={len(destinations)}"
        )

        for dest in destinations:
            chat_id = dest["chat_id"]
            template = dest.get("caption_template", "Update: {timestamp}")
            token = dest.get("token", default_token)

            if not token:
                logger.error(f"[Publish] No token configured for destination chat_id: {chat_id}")
                continue

            # Mask token for logging
            masked_token = f"{token[:5]}...{token[-5:]}" if len(token) > 10 else "***"

            # Get publisher
            if token not in self.publishers:
                logger.debug(f"[Publish] Initializing publisher for token {masked_token}")
                self.publishers[token] = TelegramPublisher(token)
            pub = self.publishers[token]

            # Format caption
            caption = template.format(
                timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sha12=new_hash[:12],
                count=build_result.get("count", "?"),
                format=fmt,
            )

            # Log caption preview (truncated)
            caption_preview = (caption[:50] + "...") if len(caption) > 50 else caption
            logger.debug(f"[Publish] Prepared caption for {chat_id}: '{caption_preview}'")

            ext = ".txt"
            if fmt in _ZIP_FORMATS:
                ext = ".zip"
            elif fmt == "conf_lines":
                ext = ".conf"
            elif fmt.endswith(".decoded.json"):
                ext = ".json"
            elif fmt.endswith(".b64sub"):
                ext = ".txt"
            elif fmt in ("npvt", "npvtsub"):
                ext = ".txt"

            # Filename
            filename = f"{route_name}_{fmt}_{new_hash[:8]}{ext}"

            try:
                start_time = time.time()
                logger.info(f"[Publish] Publishing '{filename}' to chat {chat_id} (token {masked_token})")

                # We assume publish returns nothing or checks internally
                pub.publish(chat_id, data, filename, caption)

                published_any = True
                duration = time.time() - start_time
                logger.info(f"[Publish] Successfully published to {chat_id} (Took: {duration:.2f}s)")
            except Exception as e:
                logger.error(f"[Publish] Failed to publish to {chat_id}: {e}")

        if published_any:
            self.state_repo.mark_published(unique_id, new_hash)
            logger.info(f"[Publish] Published {unique_id} ({new_hash}) successfully. State updated.")
        else:
            logger.warning(f"[Publish] Failed to publish {unique_id} to any destination.")
