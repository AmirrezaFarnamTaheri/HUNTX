from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


_DESTINATION_MODE_ALIASES = {
    "telegram": "telegram",
    "post_on_change": "telegram",
}


def normalize_destination_mode(value: Any) -> str:
    """Return the canonical transport mode for a configured destination.

    ``post_on_change`` is the historical public configuration spelling. The
    publisher has always used content hashes to suppress unchanged deliveries,
    so it is a policy alias for the Telegram transport rather than a separate
    transport implementation.
    """

    normalized = "telegram" if value is None else str(value).strip().lower()
    try:
        return _DESTINATION_MODE_ALIASES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_DESTINATION_MODE_ALIASES))
        raise ValueError(f"Unsupported destination mode: {normalized!r}; supported values: {supported}") from exc


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
        """Coerce ``api_id`` to an int, treating absent values as optional.

        An unset, empty, or zero value is a legitimately *absent* credential
        (e.g. a dev/test run without Telegram access) and maps to ``None``.
        A non-empty value that cannot be parsed as an integer — such as a
        typo or an unexpanded ``${...}`` placeholder — is a genuine
        configuration error and is rejected loudly rather than silently
        discarded.
        """
        if v is None or v == "" or v == 0:
            return None
        try:
            parsed = int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid api_id (must be an integer): {v!r}") from exc
        # A string like "0" fails the `v == 0` check above (str != int in
        # Python), so it reaches int() and must be normalized here too —
        # otherwise the documented "zero maps to None" contract is broken
        # for any zero value that arrives as text (env var, YAML string).
        return None if parsed == 0 else parsed


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

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, value: Any) -> str:
        return normalize_destination_mode(value)


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
