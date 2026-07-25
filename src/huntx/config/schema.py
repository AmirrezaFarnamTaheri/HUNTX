from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceTrustState(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class PublicationTier(str, Enum):
    RAW = "raw"
    COMPATIBLE = "compatible"
    SECURE = "secure"


class TelegramSourceConfig(BaseModel):
    token: Optional[str] = None
    chat_id: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        if ":" not in str(v):
            return None
        return str(v)


class TelegramUserSourceConfig(BaseModel):
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    session: Optional[str] = None
    peer: str

    @field_validator("api_id", mode="before")
    @classmethod
    def validate_api_id(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or v == 0:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str) and (v.isdigit() or (v.startswith("-") and v[1:].isdigit())):
            return int(v)
        raise ValueError(f"Invalid api_id: {v}")


class SourceSelector(BaseModel):
    include_formats: List[str]


class SourceConfig(BaseModel):
    id: str
    type: str
    selector: Optional[SourceSelector] = None
    telegram: Optional[TelegramSourceConfig] = None
    telegram_user: Optional[TelegramUserSourceConfig] = None
    trust_state: SourceTrustState = SourceTrustState.APPROVED
    discovered_from: Optional[str] = None
    approval_evidence: List[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("telegram", "telegram_user", "v2ray_collector"):
            raise ValueError(f"Unknown source type: {v}")
        return v

    @model_validator(mode="after")
    def validate_source_governance(self) -> "SourceConfig":
        if self.trust_state == SourceTrustState.APPROVED and self.discovered_from:
            if not self.approval_evidence:
                raise ValueError("Discovered sources cannot be approved without approval_evidence")
        return self

    @property
    def publication_eligible(self) -> bool:
        return self.trust_state == SourceTrustState.APPROVED


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
    publication_tier: PublicationTier = PublicationTier.COMPATIBLE
    require_fresh_probe: Optional[bool] = None

    @property
    def effective_require_fresh_probe(self) -> bool:
        if self.require_fresh_probe is not None:
            return self.require_fresh_probe
        return self.publication_tier == PublicationTier.SECURE


class PublishingConfig(BaseModel):
    routes: List[PublishRoute]


class AppConfig(BaseModel):
    sources: List[SourceConfig]
    publishing: PublishingConfig

    @property
    def routes(self) -> List[PublishRoute]:
        return self.publishing.routes
