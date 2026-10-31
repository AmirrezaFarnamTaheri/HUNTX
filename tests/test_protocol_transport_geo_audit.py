"""Regression matrix for protocol fidelity, reachability and offline attribution.

All fixtures are synthetic.  Never store real proxy credentials in test output.
"""
from __future__ import annotations

import base64
import json

import pytest

from huntx.core.latency_benchmarker import _tcp_probe_target
from huntx.core.remark_geoip import (
    _load_asn_ranges,
    _load_ranges,
    estimate_as_organization,
    estimate_country,
)
from huntx.formats.common.singbox import build_outbound, parse_proxy_uri


UUID = "11111111-2222-4333-8444-555555555555"


def _vmess(**updates: object) -> str:
    payload: dict[str, object] = {
        "v": "2", "ps": "fixture", "add": "edge.example.com",
        "port": "443", "id": UUID, "net": "ws", "path": "/ws",
        "host": "cdn.example.com", "tls": "tls",
    }
    payload.update(updates)
    token = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return "vmess://" + token


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@edge.example.com:443?security=tls&encryption=aes-128-gcm#unsupported-crypto",
    f"vless://{UUID}@edge.example.com:443?security=tls&type=xhttp#unsupported-xhttp",
    f"vless://{UUID}@edge.example.com:443?security=tls&type=tcp&headerType=http#legacy-http-header",
    f"vless://{UUID}@edge.example.com:443?security=reality&type=tcp#missing-reality-key",
    f"vless://{UUID}@edge.example.com:443?security=tls&pbk=bogus#conflicting-reality",
    "trojan://secret@edge.example.com:443?security=tls&type=kcp#unsupported-kcp",
    _vmess(net="xhttp"),
    _vmess(net="tcp", type="http"),
    _vmess(tls="reality"),
])
def test_unrepresentable_crypto_and_transport_do_not_silently_downgrade(uri):
    """Unsupported security/transport must not silently become RAW/plain TCP."""
    assert parse_proxy_uri(uri) is None


@pytest.mark.parametrize("uri", [
    "hysteria2://secret@edge.example.com:443?obfs=unknown&obfs-password=value",
    "hysteria2://secret@edge.example.com:443?mport=abc",
    "hysteria2://secret@edge.example.com:443?mport=300-200",
    "hysteria2://secret@edge.example.com:443?mport=443,65536",
])
def test_hysteria2_rejects_unsupported_obfuscation_and_invalid_hopping(uri):
    assert parse_proxy_uri(uri) is None


def test_hysteria2_valid_port_hopping_survives_conversion():
    node = parse_proxy_uri(
        "hy2://secret@edge.example.com:443?mport=443,445-446&obfs=salamander&obfs-password=value"
    )
    assert node is not None
    assert node.type == "hysteria2"
    outbound = build_outbound(node)
    assert outbound["server_ports"] == ["443", "445:446"]
    assert outbound["obfs"] == {"type": "salamander", "password": "value"}


def test_vmess_tls_spelling_does_not_downgrade_to_plaintext():
    node = parse_proxy_uri(_vmess(tls="TLS"))
    assert node is not None
    assert build_outbound(node)["tls"]["enabled"] is True


@pytest.mark.parametrize(("uri", "type_name", "tls_expected"), [
    (f"vless://{UUID}@edge.example.com:443?security=reality&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sni=edge.example.com&type=grpc", "vless", True),
    (_vmess(), "vmess", True),
    ("ss://aes-128-gcm:pass@edge.example.com:8388#ss", "shadowsocks", False),
    ("trojan://secret@edge.example.com:443?security=tls&type=ws&path=%2Fws", "trojan", True),
    ("hysteria2://secret@edge.example.com:443", "hysteria2", True),
    ("hysteria://secret@edge.example.com:443?upmbps=50&downmbps=50", "hysteria", True),
    ("tuic://"+UUID+":password@edge.example.com:443", "tuic", True),
    ("anytls://password@edge.example.com:443", "anytls", True),
    ("socks5://alice:password@edge.example.com:1080", "socks", False),
    ("https://alice:password@edge.example.com:8443", "http", True),
    ("ssh://alice@edge.example.com", "ssh", False),
])
def test_supported_protocols_preserve_type_and_tls_intent(uri, type_name, tls_expected):
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.type == type_name
    assert node.tls_enabled is tls_expected


def test_wireguard_is_explicitly_unrepresentable_as_legacy_singbox_outbound():
    # sing-box 1.13+ uses an endpoint with peer/local keys, not a bare outbound.
    assert parse_proxy_uri("wireguard://privatekey@edge.example.com:51820") is None


def test_tcp_endpoint_probes_decode_shadowsocks_and_ssh_default_port():
    ss = base64.urlsafe_b64encode(
        b"aes-128-gcm:synthetic-password@edge.example.com:8388"
    ).decode("ascii").rstrip("=")
    assert _tcp_probe_target("ss://" + ss) == ("edge.example.com", 8388)
    assert _tcp_probe_target("ssh://alice@edge.example.com") == ("edge.example.com", 22)
    assert _tcp_probe_target("hysteria2://secret@edge.example.com:443") is None


def test_encoded_vmess_quic_is_not_mislabeled_or_tcp_probed():
    """An encoded QUIC transport must not be reported as TCP-unreachable."""
    from huntx.core.endpoint_intelligence import describe_proxy_endpoint

    link = _vmess(net="quic", tls="tls")
    assert _tcp_probe_target(link) is None
    evidence = describe_proxy_endpoint(link)
    assert evidence is not None
    assert evidence["transport_kind"] == "udp"
    assert "udp_requires_native_protocol_probe" in evidence["diagnostic_findings"]


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@edge.example.com:443?security=tls&type=quic",
    "socks5://alice:password@edge.example.com:1080?network=udp",
])
def test_declared_udp_transport_is_not_mislabeled_as_tcp(uri):
    from huntx.core.endpoint_intelligence import describe_proxy_endpoint

    evidence = describe_proxy_endpoint(uri)
    assert evidence is not None
    assert evidence["transport_kind"] == "udp"
    assert "udp_requires_native_protocol_probe" in evidence["diagnostic_findings"]


def test_country_and_asn_overlapping_tables_fall_back_to_outer_range(tmp_path, monkeypatch):
    """Lookup within a broad prefix must survive a shorter nested range ending."""
    country = tmp_path / "country.csv"
    country.write_text(
        "11.0.0.0,11.0.0.255,US\n"
        "11.0.0.64,11.0.0.95,DE\n",
        encoding="utf-8",
    )
    asn = tmp_path / "asn.csv"
    asn.write_text(
        '11.0.0.0,11.0.0.255,64500,"Outer Operator"\n'
        '11.0.0.64,11.0.0.95,64501,"Nested Operator"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HUNTX_GEOIP_IPV4_CSV", str(country))
    monkeypatch.setenv("HUNTX_ASN_IPV4_CSV", str(asn))
    _load_ranges.cache_clear()
    _load_asn_ranges.cache_clear()
    try:
        assert estimate_country("11.0.0.80") == "DE"
        assert estimate_country("11.0.0.100") == "US"
        assert estimate_as_organization("11.0.0.80") == "Nested Operator"
        assert estimate_as_organization("11.0.0.100") == "Outer Operator"
        assert estimate_country("11.0.1.1") is None
    finally:
        _load_ranges.cache_clear()
        _load_asn_ranges.cache_clear()
