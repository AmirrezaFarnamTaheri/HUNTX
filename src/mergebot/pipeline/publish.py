import logging
import datetime
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

        # Check if changed
        last_hash = self.state_repo.get_last_published_hash(route_name)
        if last_hash == new_hash:
            logger.info(f"No change for {route_name}, skipping publish.")
            return

        # Publish to all destinations
        # We need tokens. Assuming destination config has 'token' or we use global?
        # The prompt config structure:
        # destinations:
        #   - chat_id: "..."
        #     mode: post_on_change
        #     caption_template: ...
        # But where is the token?
        # The source config has token.
        # Usually publishers need a token.
        # PROPOSAL: Add 'token' to destination config OR use env var.
        # The PROMPT config example doesn't show token in destination.
        # But it shows "sources ... telegram ... token".
        # Maybe we reuse the source token? Or we need a default bot token?
        # I'll assume we can pass a token in destination OR use a default one from env.
        # Let's check config.prod.yaml again.
        # It doesn't show token in publishing.
        # I will assume there is a global or per-destination token.
        # I will use os.getenv("TELEGRAM_TOKEN") as fallback.

        import os
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
                count=build_result.get("count", "?")
            )

            # Filename
            # Heuristic extension
            ext = ".txt"
            # Try to guess from route formats?
            # If route name implies extension...
            filename = f"{route_name}_{new_hash[:8]}{ext}"

            try:
                pub.publish(chat_id, build_result["data"], filename, caption)
                published_any = True
            except Exception:
                logger.error(f"Failed to publish to {chat_id}")

        if published_any:
            self.state_repo.mark_published(route_name, new_hash)
            logger.info(f"Published {route_name} ({new_hash})")
