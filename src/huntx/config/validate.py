import os

from .schema import AppConfig
from ..formats.registry import FormatRegistry


_DERIVED_FORMATS = {"b64sub", "decoded.json", "singbox.json"}
_DERIVED_SUFFIXES = (".b64sub", ".decoded.json", ".singbox.json")


def _configured_publish_token(destination_token: str | None) -> str | None:
    """Resolve destination-specific credentials using runtime precedence."""
    return destination_token or os.getenv("PUBLISH_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")


def _validate_route_format(registry: FormatRegistry, route_name: str, fmt: str) -> None:
    """Validate one requested output format against actual build capability."""
    if not fmt:
        raise ValueError(f"Route {route_name} has empty format ID")

    registered = set(registry.list_formats())
    if fmt in registered:
        if not registry.can_build(fmt):
            raise ValueError(
                f"Route {route_name} format {fmt!r} is parse-only and cannot build artifacts"
            )
        return

    if fmt in _DERIVED_FORMATS:
        return

    for suffix in _DERIVED_SUFFIXES:
        if fmt.endswith(suffix):
            base_fmt = fmt[: -len(suffix)]
            if base_fmt in registered or base_fmt in {"npvt", "npvtsub"}:
                return

    raise ValueError(f"Route {route_name} has unrecognized format ID: {fmt}")


def validate_config(config: AppConfig):
    """Perform deep validation of application configuration."""
    registry = FormatRegistry.get_instance()
    if not registry.list_formats():
        try:
            from ..store.raw_store import RawStore
            from ..formats.register_builtin import register_all_formats

            register_all_formats(registry, RawStore())
        except Exception:
            # The loader can run in dry tests where a RawStore cannot be created.
            # Unknown formats will still fail below instead of being accepted.
            pass

    is_strict = os.getenv("HUNTX_STRICT", "0") in ("1", "true", "TRUE") or os.getenv(
        "CI", "0"
    ) in ("1", "true", "TRUE")

    seen_ids = set()
    for source in config.sources:
        if not source.id or source.id.startswith("${"):
            raise ValueError(f"Source has invalid/unexpanded ID: {source.id}")
        if source.id in seen_ids:
            raise ValueError(f"Duplicate source ID: {source.id}")
        seen_ids.add(source.id)

        if source.type == "telegram":
            if not source.telegram:
                raise ValueError(
                    f"Source {source.id} is type='telegram' but missing 'telegram' block"
                )
            if source.telegram_user:
                raise ValueError(
                    f"Source {source.id} is type='telegram' but has forbidden "
                    "'telegram_user' block"
                )
            if is_strict and (
                not source.telegram.token or source.telegram.token.startswith("${")
            ):
                raise ValueError(
                    f"Source {source.id} has invalid/unexpanded telegram token"
                )
            if not source.telegram.chat_id or source.telegram.chat_id.startswith("${"):
                raise ValueError(
                    f"Source {source.id} has invalid/unexpanded telegram chat_id"
                )

        elif source.type == "telegram_user":
            if not source.telegram_user:
                raise ValueError(
                    f"Source {source.id} is type='telegram_user' but missing "
                    "'telegram_user' block"
                )
            if source.telegram:
                raise ValueError(
                    f"Source {source.id} is type='telegram_user' but has forbidden "
                    "'telegram' block"
                )
            if is_strict:
                if not source.telegram_user.api_id:
                    raise ValueError(f"Source {source.id} missing telegram_user api_id")
                if (
                    not source.telegram_user.api_hash
                    or source.telegram_user.api_hash.startswith("${")
                ):
                    raise ValueError(
                        f"Source {source.id} has invalid/unexpanded telegram_user api_hash"
                    )
                if (
                    not source.telegram_user.session
                    or source.telegram_user.session.startswith("${")
                ):
                    raise ValueError(
                        f"Source {source.id} has invalid/unexpanded telegram_user session"
                    )
            if (
                not source.telegram_user.peer
                or source.telegram_user.peer.startswith("${")
            ):
                raise ValueError(
                    f"Source {source.id} has invalid/unexpanded telegram_user peer"
                )
        else:
            raise ValueError(f"Source {source.id} has unknown type: {source.type}")

    for route in config.routes:
        if not route.name or route.name.startswith("${"):
            raise ValueError(f"Route name cannot be empty or unexpanded: {route.name}")

        if not route.from_sources:
            raise ValueError(f"Route {route.name} has no sources specified")

        for source_ref in route.from_sources:
            if source_ref not in seen_ids:
                raise ValueError(
                    f"Route {route.name} references unknown source {source_ref}"
                )

        if not route.formats:
            raise ValueError(f"Route {route.name} has no formats specified")

        for fmt in route.formats:
            _validate_route_format(registry, route.name, fmt)

        for destination in route.destinations:
            if destination.mode != "telegram":
                raise ValueError(
                    f"Route {route.name} has unsupported destination mode: "
                    f"{destination.mode}"
                )
            if not destination.chat_id or destination.chat_id.startswith("${"):
                raise ValueError(
                    f"Route {route.name} destination missing or invalid chat_id: "
                    f"{destination.chat_id}"
                )

            resolved_token = _configured_publish_token(destination.token)
            if is_strict:
                if not resolved_token or resolved_token.startswith("${"):
                    raise ValueError(
                        f"Route {route.name} destination missing/unexpanded token in "
                        "strict mode; configure destination.token, PUBLISH_BOT_TOKEN, "
                        "or TELEGRAM_TOKEN"
                    )
            elif destination.token and destination.token.startswith("${"):
                raise ValueError(
                    f"Route {route.name} destination has invalid unexpanded token: "
                    f"{destination.token}"
                )
