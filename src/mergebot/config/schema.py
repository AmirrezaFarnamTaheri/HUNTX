from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class TelegramSourceConfig:
    token: str
    chat_id: str

@dataclass
class TelegramUserSourceConfig:
    api_id: int
    api_hash: str
    session: str
    peer: str

@dataclass
class SourceSelector:
    include_formats: List[str]

@dataclass
class SourceConfig:
    id: str
    type: str
    selector: SourceSelector
    telegram: Optional[TelegramSourceConfig] = None
    telegram_user: Optional[TelegramUserSourceConfig] = None

@dataclass
class DestinationConfig:
    chat_id: str
    mode: str
    caption_template: str
    token: Optional[str] = None

@dataclass
class PublishRoute:
    name: str
    from_sources: List[str]
    formats: List[str]
    destinations: List[DestinationConfig]

@dataclass
class AppConfig:
    sources: List[SourceConfig]
    routes: List[PublishRoute]
