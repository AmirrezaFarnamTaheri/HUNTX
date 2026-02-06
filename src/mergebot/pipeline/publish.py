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

        # Check if changed using unique_id (route + format)
        last_hash = self.state_repo.get_last_published_hash(unique_id)
        if last_hash == new_hash:
            logger.info(f"No change for {unique_id}, skipping publish.")
            return

        default_token = os.getenv("TELEGRAM_TOKEN")
        published_any = False

        for dest in destinations:
            chat_id = dest["chat_id"]
            template = dest.get("caption_template", "Update: {timestamp}")
            token = dest.get("token", default_token)

            if not token:
                logger.error("No token for destination")
                continue

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
                pub.publish(chat_id, build_result["data"], filename, caption)
                published_any = True
            except Exception as e:
                logger.error(f"Failed to publish to {chat_id}: {e}")

        if published_any:
            self.state_repo.mark_published(unique_id, new_hash)
            logger.info(f"Published {unique_id} ({new_hash})")
