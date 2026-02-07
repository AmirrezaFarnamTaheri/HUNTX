from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class TelegramSourceConfig(BaseModel):
    token: str
    chat_id: str

    @validator('token')
    def validate_token(cls, v):
        if ':' not in v:
            raise ValueError('Invalid Telegram Bot Token format (missing colon)')
        return v

class TelegramUserSourceConfig(BaseModel):
    api_id: int
    api_hash: str
    session: str
    peer: str

class SourceSelector(BaseModel):
    include_formats: List[str]

class SourceConfig(BaseModel):
    id: str
    type: str
    selector: Optional[SourceSelector] = None
    telegram: Optional[TelegramSourceConfig] = None
    telegram_user: Optional[TelegramUserSourceConfig] = None

    @validator('type')
    def validate_type(cls, v):
        if v not in ('telegram', 'telegram_user'):
            raise ValueError(f"Unknown source type: {v}")
        return v

class DestinationConfig(BaseModel):
    chat_id: str
    mode: str = "telegram"
    caption_template: str = "{filename}"
    token: Optional[str] = None

class PublishRoute(BaseModel):
    name: str
    from_sources: List[str]
    formats: List[str]
    destinations: List[DestinationConfig]

class PublishingConfig(BaseModel):
    routes: List[PublishRoute]

class AppConfig(BaseModel):
    sources: List[SourceConfig]
    # 'routes' are nested under 'publishing' key in YAML
    publishing: PublishingConfig

    @property
    def routes(self) -> List[PublishRoute]:
        """Helper to access routes directly"""
        return self.publishing.routes
