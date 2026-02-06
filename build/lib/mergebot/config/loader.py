import yaml
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path
from .env_expand import expand_env
from .schema import AppConfig, SourceConfig, TelegramSourceConfig, SourceSelector, PublishRoute, DestinationConfig

logger = logging.getLogger(__name__)

def load_config(path: Path) -> AppConfig:
    logger.info(f"Loading configuration from {path}")

    if not os.path.exists(path):
        logger.error(f"Config file not found: {path}")
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, "r") as f:
            raw_text = f.read()

        expanded_text = expand_env(raw_text)
        data = yaml.safe_load(expanded_text)

        if not data:
            logger.error("Config file is empty or invalid YAML")
            raise ValueError("Config file is empty or invalid YAML")

        # Parse sources
        sources = []
        for i, s in enumerate(data.get("sources", [])):
            tg_conf = None
            telegram_data = s.get("telegram")

            source_id = s.get("id", f"unknown_source_{i}")

            if telegram_data:
                tg_token = telegram_data.get("token")
                tg_chat_id = telegram_data.get("chat_id")

                if not tg_token or not tg_chat_id:
                    logger.warning(f"Skipping source '{source_id}' (index {i}): Missing Telegram token or chat_id. Check environment variables.")
                    continue
                tg_conf = TelegramSourceConfig(token=tg_token, chat_id=tg_chat_id)

            source_type = s.get("type")
            selector_data = s.get("selector", {})
            include_formats = selector_data.get("include_formats")

            if not all([source_id, source_type, include_formats is not None]):
                logger.error(f"Source at index {i} is missing required fields: 'id', 'type', or 'selector.include_formats'.")
                raise ValueError(f"Source at index {i} is missing required fields.")

            logger.debug(f"Loaded source config: {source_id} ({source_type})")
            sources.append(SourceConfig(
                id=source_id,
                type=source_type,
                selector=SourceSelector(include_formats=include_formats),
                telegram=tg_conf
            ))

        # Parse routes
        routes = []
        for i, r in enumerate(data.get("publishing", {}).get("routes", [])):
            route_name = r.get("name", f"route_{i}")
            dests = []
            for d in r.get("destinations", []):
                dests.append(DestinationConfig(
                    chat_id=d.get("chat_id"),
                    mode=d.get("mode"),
                    caption_template=d.get("caption_template", ""),
                    token=d.get("token")
                ))

            logger.debug(f"Loaded route config: {route_name} with {len(dests)} destinations")
            routes.append(PublishRoute(
                name=route_name,
                from_sources=r.get("from_sources", []),
                formats=r.get("formats", []),
                destinations=dests
            ))

        logger.info(f"Configuration loaded successfully: {len(sources)} sources, {len(routes)} routes.")
        return AppConfig(sources=sources, routes=routes)

    except Exception as e:
        logger.exception(f"Failed to load configuration: {e}")
        raise
