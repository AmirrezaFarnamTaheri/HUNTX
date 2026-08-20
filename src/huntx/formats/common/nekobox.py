"""Render NekoBox-compatible sing-box outbound subscriptions."""

from __future__ import annotations

import json

from .singbox import config_from_uris

_NEKOBOX_EXCLUDED_TYPES = {"selector", "urltest", "direct"}


def _proxy_only_outbound(outbound: dict) -> dict | None:
    """Return a NekoBox-safe proxy outbound without config-local dependencies."""
    if outbound.get("type") in _NEKOBOX_EXCLUDED_TYPES:
        return None
    cleaned = dict(outbound)
    cleaned.pop("domain_resolver", None)
    return cleaned


def build_nekobox_outbounds_bytes(text: str) -> bytes:
    """Render a NekoBox subscription object containing proxy-only sing-box outbounds."""
    try:
        config = config_from_uris(text.splitlines())
    except AttributeError:
        return b""

    proxy_outbounds = [
        cleaned
        for outbound in config.get("outbounds", [])
        if isinstance(outbound, dict)
        for cleaned in [_proxy_only_outbound(outbound)]
        if cleaned is not None
    ]
    if not proxy_outbounds:
        return b""
    return json.dumps(
        {"outbounds": proxy_outbounds},
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
