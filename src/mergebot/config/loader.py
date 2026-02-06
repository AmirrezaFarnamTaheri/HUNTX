import yaml
from typing import Dict, Any
from pathlib import Path
from .env_expand import expand_env
from .schema import AppConfig, SourceConfig, TelegramSourceConfig, SourceSelector, PublishRoute, DestinationConfig

def load_config(path: Path) -> AppConfig:
    with open(path, "r") as f:
        raw_text = f.read()

    expanded_text = expand_env(raw_text)
    data = yaml.safe_load(expanded_text)

    # Parse sources
    sources = []
    for i, s in enumerate(data.get("sources", [])):
        tg_conf = None
        telegram_data = s.get("telegram")
        if telegram_data:
            tg_token = telegram_data.get("token")
            tg_chat_id = telegram_data.get("chat_id")
            if not tg_token or not tg_chat_id:
                raise ValueError(f"Source at index {i} is of type 'telegram' but is missing 'token' or 'chat_id'.")
            tg_conf = TelegramSourceConfig(token=tg_token, chat_id=tg_chat_id)

        source_id = s.get("id")
        source_type = s.get("type")
        selector_data = s.get("selector", {})
        include_formats = selector_data.get("include_formats")

        if not all([source_id, source_type, include_formats is not None]):
            raise ValueError(f"Source at index {i} is missing required fields: 'id', 'type', or 'selector.include_formats'.")

        sources.append(SourceConfig(
            id=source_id,
            type=source_type,
            selector=SourceSelector(include_formats=include_formats),
            telegram=tg_conf
        ))

    # Parse routes
    routes = []
    for i, r in enumerate(data.get("publishing", {}).get("routes", [])):
        dests = []
        for d in r.get("destinations", []):
            dests.append(DestinationConfig(
                chat_id=d.get("chat_id"),
                mode=d.get("mode"),
                caption_template=d.get("caption_template", ""),
                token=d.get("token")
            ))

        routes.append(PublishRoute(
            name=r.get("name"),
            from_sources=r.get("from_sources", []),
            formats=r.get("formats", []),
            destinations=dests
        ))

    return AppConfig(sources=sources, routes=routes)
