"""Render NekoBox-compatible sing-box node feeds as top-level outbound arrays."""

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
    """Render a NekoBox node feed: a top-level array of proxy-only outbounds.

    NekoBox and similar clients import a subscription-style top-level JSON
    array as individual selectable nodes. Wrapping the nodes inside a
    configuration-shaped ``{"outbounds": [...]}`` object made the whole
    artifact import as one custom JSON configuration instead of expanding
    the nodes.
    """
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
        proxy_outbounds,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
