"""Render proxy share URIs as a NekoBox-compatible sing-box outbound array."""

from __future__ import annotations

import json
from typing import Any

from .singbox import config_from_uris

_SPECIAL_OUTBOUND_TYPES = {"selector", "urltest", "direct"}


def outbounds_from_uris(uris: list[str]) -> list[dict[str, Any]]:
    """Return only importable proxy outbounds, without config-local dependencies."""
    config = config_from_uris(uris)
    outbounds: list[dict[str, Any]] = []
    for outbound in config.get("outbounds", []):
        if outbound.get("type") in _SPECIAL_OUTBOUND_TYPES:
            continue
        clean = dict(outbound)
        clean.pop("domain_resolver", None)
        outbounds.append(clean)
    return outbounds


def build_nekobox_outbounds_bytes(text: str) -> bytes:
    """Render proxy text as a NekoBox-compatible JSON array of sing-box outbounds."""
    try:
        outbounds = outbounds_from_uris(text.splitlines())
    except AttributeError:
        return b""
    if not outbounds:
        return b""
    return json.dumps(outbounds, indent=2, ensure_ascii=False).encode("utf-8")
