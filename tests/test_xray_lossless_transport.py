from __future__ import annotations

import json

from huntx.formats.common.xray import build_xray_config_bytes


def _proxy_outbounds(raw: bytes) -> list[dict]:
    if not raw:
        return []
    config = json.loads(raw.decode("utf-8"))
    return [item for item in config["outbounds"] if item.get("protocol") != "freedom"]


def test_xray_skips_vless_xhttp_instead_of_downgrading_to_raw():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&sni=example.com&type=xhttp&path=%2Fapi#xhttp"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_skips_tcp_http_obfuscation_instead_of_dropping_header_settings():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:80"
        "?security=none&type=tcp&headerType=http&host=example.com#http-obfs"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_skips_vless_non_default_encryption_instead_of_forcing_none():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp&encryption=aes-128-gcm#non-default-encryption"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_skips_vless_explicit_empty_encryption_instead_of_forcing_none():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp&encryption=#empty-encryption"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []
