"""TLS SNI, WebSocket host and ALPN must retain separate meanings."""
from __future__ import annotations

import base64
import json

import pytest

from huntx.formats.common.singbox import build_outbound, parse_proxy_uri

UUID = "11111111-2222-4333-8444-555555555555"


def _vmess(*, net="ws", host="front.example.net", sni="", alpn="", tls="tls"):
    payload = {
        "v": "2", "ps": "synthetic", "add": "origin.example.net",
        "port": "443", "id": UUID, "net": net,
        "host": host, "sni": sni, "alpn": alpn, "tls": tls,
        "path": "/ws", "type": "none",
    }
    return "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@origin.example.net:443?security=TLS&type=ws&host=front.example.net",
    "trojan://synthetic@origin.example.net:443?security=TLS&type=ws&host=front.example.net",
    _vmess(tls="TLS"),
])
def test_tls_casing_never_downgrades_to_plaintext(uri):
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.tls_enabled is True
    assert build_outbound(node)["tls"]["enabled"] is True


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@origin.example.net:443?security=tls&type=ws&host=front.example.net",
    "trojan://synthetic@origin.example.net:443?security=tls&type=httpupgrade&host=front.example.net",
    _vmess(host="front.example.net"),
])
def test_transport_http_host_is_not_an_implicit_certificate_sni(uri):
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.tls_server_name == ""
    tls = build_outbound(node)["tls"]
    assert "server_name" not in tls
    assert node.transport_host == ["front.example.net"]


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@origin.example.net:443?security=tls&type=ws&host=front.example.net&sni=cert.example.net",
    _vmess(host="front.example.net", sni="cert.example.net"),
])
def test_explicit_certificate_sni_is_not_replaced_by_websocket_host(uri):
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.tls_server_name == "cert.example.net"
    outbound = build_outbound(node)
    assert outbound["tls"]["server_name"] == "cert.example.net"
    assert node.transport_host == ["front.example.net"]


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@origin.example.net:443?security=tls&type=grpc&alpn=http%2F1.1&serviceName=test",
    "trojan://synthetic@origin.example.net:443?security=tls&type=grpc&alpn=http%2F1.1",
    _vmess(net="grpc", alpn="http/1.1"),
])
def test_explicit_incompatible_grpc_alpn_is_not_exported_as_viable(uri):
    assert parse_proxy_uri(uri) is None


@pytest.mark.parametrize("uri", [
    f"vless://{UUID}@origin.example.net:443?security=tls&type=grpc&alpn=h2%2Chttp%2F1.1&serviceName=test",
    _vmess(net="grpc", alpn="h2,http/1.1"),
])
def test_explicit_grpc_h2_is_representable(uri):
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.transport_type == "grpc"
    assert "h2" in build_outbound(node)["tls"]["alpn"]


def test_proxy_tls_verification_override_is_never_silent():
    uri = f"vless://{UUID}@origin.example.net:443?security=tls&insecure=1&sni=cert.example.net"
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.tls_insecure is True
    assert build_outbound(node)["tls"]["insecure"] is True
