import os

from .schema import AppConfig
from ..formats.registry import FormatRegistry


def _configured_publish_token(destination_token: str | None) -> str | None:
    """Resolve destination-specific credentials using runtime precedence."""

    return destination_token or os.getenv("PUBLISH_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")


def validate_config(config: AppConfig):
    """
    Perform deep validation of the application configuration.
    Ensures:
    - Unique source IDs
    - All routes reference existing sources
    - Source blocks (telegram, telegram_user) match their type and exclude the other
    - Required fields are non-empty and do not have unexpanded environment variables
    - Formats in routes are recognized by the registry (or are valid derived formats)
    - Destination modes are canonical and supported
    - If strict mode is active (HUNTX_STRICT=1 or CI=true), publishing credentials
      are resolved with the same destination > PUBLISH_BOT_TOKEN > TELEGRAM_TOKEN
      precedence used at runtime
    """
    registry = FormatRegistry.get_instance()
    # Populates registry dynamically if empty to validate formats during loader phase
    if not registry.list_formats():
        try:
            from ..store.raw_store import RawStore
            from ..formats.register_builtin import register_all_formats

            register_all_formats(registry, RawStore())
        except Exception:
            # Fallback if raw store cannot be created (e.g. inside dry tests)
            pass

    is_strict = os.getenv("HUNTX_STRICT", "0") in ("1", "true", "TRUE") or os.getenv("CI", "0") in (
        "1",
        "true",
        "TRUE",
    )

    seen_ids = set()
    for s in config.sources:
        if not s.id or s.id.startswith("${"):
            raise ValueError(f"Source has invalid/unexpanded ID: {s.id}")
        if s.id in seen_ids:
            raise ValueError(f"Duplicate source ID: {s.id}")
        seen_ids.add(s.id)

        # Type-specific validation
        if s.type == "telegram":
            if not s.telegram:
                raise ValueError(f"Source {s.id} is type='telegram' but missing 'telegram' block")
            if s.telegram_user:
                raise ValueError(f"Source {s.id} is type='telegram' but has forbidden 'telegram_user' block")
            if is_strict and (not s.telegram.token or s.telegram.token.startswith("${")):
                raise ValueError(f"Source {s.id} has invalid/unexpanded telegram token")
            if not s.telegram.chat_id or s.telegram.chat_id.startswith("${"):
                raise ValueError(f"Source {s.id} has invalid/unexpanded telegram chat_id")

        elif s.type == "telegram_user":
            if not s.telegram_user:
                raise ValueError(f"Source {s.id} is type='telegram_user' but missing 'telegram_user' block")
            if s.telegram:
                raise ValueError(f"Source {s.id} is type='telegram_user' but has forbidden 'telegram' block")
            if is_strict:
                if not s.telegram_user.api_id:
                    raise ValueError(f"Source {s.id} missing telegram_user api_id")
                if not s.telegram_user.api_hash or s.telegram_user.api_hash.startswith("${"):
                    raise ValueError(f"Source {s.id} has invalid/unexpanded telegram_user api_hash")
                if not s.telegram_user.session or s.telegram_user.session.startswith("${"):
                    raise ValueError(f"Source {s.id} has invalid/unexpanded telegram_user session")
            if not s.telegram_user.peer or s.telegram_user.peer.startswith("${"):
                raise ValueError(f"Source {s.id} has invalid/unexpanded telegram_user peer")
        else:
            raise ValueError(f"Source {s.id} has unknown type: {s.type}")

    for r in config.routes:
        if not r.name or r.name.startswith("${"):
            raise ValueError(f"Route name cannot be empty or unexpanded: {r.name}")

        if not r.from_sources:
            raise ValueError(f"Route {r.name} has no sources specified")

        for src_ref in r.from_sources:
            if src_ref not in seen_ids:
                raise ValueError(f"Route {r.name} references unknown source {src_ref}")

        if not r.formats:
            raise ValueError(f"Route {r.name} has no formats specified")

        for fmt in r.formats:
            if not fmt:
                raise ValueError(f"Route {r.name} has empty format ID")

            is_valid_fmt = False
            # Check if format is registered or a valid derived/known format
            if fmt in registry.list_formats() or fmt in ["b64sub", "decoded.json", "singbox.json"]:
                is_valid_fmt = True
            else:
                # check derived formats
                for suffix in [".b64sub", ".decoded.json", ".singbox.json"]:
                    if fmt.endswith(suffix):
                        base_fmt = fmt[: -len(suffix)]
                        if base_fmt in registry.list_formats() or base_fmt in ["npvt", "npvtsub"]:
                            is_valid_fmt = True
                            break
            if not is_valid_fmt:
                raise ValueError(f"Route {r.name} has unrecognized format ID: {fmt}")

        for d in r.destinations:
            if d.mode != "telegram":
                # DestinationConfig normalizes supported aliases before this point.
                raise ValueError(f"Route {r.name} has unsupported destination mode: {d.mode}")
            if not d.chat_id or d.chat_id.startswith("${"):
                raise ValueError(f"Route {r.name} destination missing or invalid chat_id: {d.chat_id}")

            resolved_token = _configured_publish_token(d.token)
            if is_strict:
                if not resolved_token or resolved_token.startswith("${"):
                    raise ValueError(
                        f"Route {r.name} destination missing/unexpanded token in strict mode; "
                        "configure destination.token, PUBLISH_BOT_TOKEN, or TELEGRAM_TOKEN"
                    )
            elif d.token and d.token.startswith("${"):
                raise ValueError(f"Route {r.name} destination has invalid unexpanded token: {d.token}")
