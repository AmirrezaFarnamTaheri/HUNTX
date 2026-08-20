from __future__ import annotations

import base64
import json

from huntx.formats.common.xray import build_xray_config_bytes

_VALID_REALITY_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _proxy_outbounds(raw: bytes) -> list[dict]:
    if not raw:
        return []
    config = json.loads(raw.decode("utf-8"))
    return [item for item in config["outbounds"] if item.get("protocol") != "freedom"]


def _vmess_uri(**overrides: object) -> str:
    payload: dict[str, object] = {
        "v": "2",
        "ps": "vmess",
        "add": "example.com",
        "port": "443",
        "id": "11111111-2222-3333-4444-555555555555",
        "aid": "0",
        "scy": "auto",
        "net": "tcp",
        "type": "none",
        "tls": "tls",
        "sni": "example.com",
    }
    payload.update(overrides)
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"vmess://{encoded}"


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


def test_xray_accepts_vless_absent_or_none_encryption_with_tls():
    absent = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp#absent"
    )
    explicit_none = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp&encryption=none#none"
    )

    assert len(_proxy_outbounds(build_xray_config_bytes(absent))) == 1
    assert len(_proxy_outbounds(build_xray_config_bytes(explicit_none))) == 1


def test_xray_skips_removed_allow_insecure_tls_setting():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp&allowInsecure=1#insecure"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_skips_public_plaintext_vless_and_trojan():
    vless = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:80"
        "?security=none&type=tcp#public-vless"
    )
    trojan = "trojan://secret@example.com:80?security=none&type=tcp#public-trojan"

    assert _proxy_outbounds(build_xray_config_bytes(vless)) == []
    assert _proxy_outbounds(build_xray_config_bytes(trojan)) == []


def test_xray_keeps_plaintext_vless_for_known_private_ip():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@192.168.1.10:80"
        "?security=none&type=tcp#private-vless"
    )

    outbounds = _proxy_outbounds(build_xray_config_bytes(uri))
    assert len(outbounds) == 1
    assert outbounds[0]["settings"]["address"] == "192.168.1.10"


def test_xray_rejects_invalid_vless_uuid_before_emitting_config():
    uri = "vless://not-a-uuid@example.com:443?security=tls&type=tcp#bad-uuid"

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_accepts_vision_only_over_direct_raw_tls_or_reality():
    valid = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        f"?security=reality&pbk={_VALID_REALITY_KEY}&sid=ab12"
        "&sni=cdn.example.com&flow=xtls-rprx-vision&type=tcp#vision"
    )
    invalid_grpc = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&flow=xtls-rprx-vision&type=grpc&serviceName=svc#vision-grpc"
    )

    outbounds = _proxy_outbounds(build_xray_config_bytes(valid))
    assert len(outbounds) == 1
    assert outbounds[0]["settings"]["flow"] == "xtls-rprx-vision"
    assert outbounds[0]["streamSettings"]["method"] == "raw"
    assert _proxy_outbounds(build_xray_config_bytes(invalid_grpc)) == []


def test_xray_rejects_unknown_vless_flow():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=tls&type=tcp&flow=xtls-rprx-direct#unknown-flow"
    )

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []


def test_xray_rejects_malformed_reality_credentials():
    bad_key = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?security=reality&pbk=not-a-key&sid=ab12&type=tcp#bad-key"
    )
    bad_short_id = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        f"?security=reality&pbk={_VALID_REALITY_KEY}&sid=xyz&type=tcp#bad-sid"
    )

    assert _proxy_outbounds(build_xray_config_bytes(bad_key)) == []
    assert _proxy_outbounds(build_xray_config_bytes(bad_short_id)) == []


def test_xray_rejects_vmess_features_current_xray_would_coerce_or_drop():
    legacy_alter_id = _vmess_uri(aid="1")
    plaintext_security = _vmess_uri(scy="none")

    assert _proxy_outbounds(build_xray_config_bytes(legacy_alter_id)) == []
    assert _proxy_outbounds(build_xray_config_bytes(plaintext_security)) == []


def test_xray_accepts_current_vmess_security_modes():
    for security in ("auto", "aes-128-gcm", "chacha20-poly1305"):
        outbounds = _proxy_outbounds(build_xray_config_bytes(_vmess_uri(scy=security)))
        assert len(outbounds) == 1
        assert outbounds[0]["settings"]["security"] == security


def test_xray_rejects_unsupported_shadowsocks_cipher():
    userinfo = base64.urlsafe_b64encode(b"none:password").decode("ascii").rstrip("=")
    uri = f"ss://{userinfo}@example.com:443#plain"

    assert _proxy_outbounds(build_xray_config_bytes(uri)) == []
