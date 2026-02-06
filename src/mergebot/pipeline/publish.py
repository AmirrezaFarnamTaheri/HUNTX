import logging
import datetime
import os
from typing import Dict, Any, List
from ..state.repo import StateRepo
from ..publishers.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)

class PublishPipeline:
    def __init__(self, state_repo: StateRepo):
        self.state_repo = state_repo
        self.publishers = {} # cache of (token) -> publisher

    def run(self, build_result: Dict[str, Any], destinations: List[Dict[str, Any]]):
        route_name = build_result["route_name"]
        new_hash = build_result["artifact_hash"]
        fmt = build_result.get("format", "unknown")
        unique_id = build_result.get("unique_id", route_name)

        logger.debug(f"Publishing check: {unique_id} with hash {new_hash}")

        # Check if changed using unique_id (route + format)
        last_hash = self.state_repo.get_last_published_hash(unique_id)
        if last_hash == new_hash:
            logger.info(f"No content change for {unique_id} (hash: {last_hash}), skipping publish.")
            return

        default_token = os.getenv("TELEGRAM_TOKEN")
        published_any = False

        logger.info(f"Content changed for {unique_id} ({last_hash} -> {new_hash}). Publishing to {len(destinations)} destinations.")

        for dest in destinations:
            chat_id = dest["chat_id"]
            template = dest.get("caption_template", "Update: {timestamp}")
            token = dest.get("token", default_token)

            if not token:
                logger.error(f"No token configured for destination chat_id: {chat_id}")
                continue

            # Mask token for logging
            masked_token = f"{token[:5]}...{token[-5:]}" if len(token) > 10 else "***"
            logger.debug(f"Using publisher with token {masked_token} for chat_id {chat_id}")

            # Get publisher
            if token not in self.publishers:
                self.publishers[token] = TelegramPublisher(token)
            pub = self.publishers[token]

            # Format caption
            caption = template.format(
                timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sha12=new_hash[:12],
                count=build_result.get("count", "?"),
                format=fmt
            )

            # Filename extension logic
            ext = ".txt"
            if fmt in ["ovpn"]:
                ext = ".ovpn"
            elif fmt in ["opaque_bundle"]:
                ext = ".zip"
            elif fmt in ["conf_lines"]:
                ext = ".conf"

            # Filename
            filename = f"{route_name}_{fmt}_{new_hash[:8]}{ext}"

            try:
                logger.info(f"Publishing artifact '{filename}' to Telegram chat_id: {chat_id}")
                pub.publish(chat_id, build_result["data"], filename, caption)
                published_any = True
                logger.debug(f"Successfully published to {chat_id}")
            except Exception as e:
                logger.error(f"Failed to publish to {chat_id}: {e}")

        if published_any:
            self.state_repo.mark_published(unique_id, new_hash)
            logger.info(f"Published {unique_id} ({new_hash}) successfully. State updated.")
        else:
            logger.warning(f"Failed to publish {unique_id} to any destination.")
