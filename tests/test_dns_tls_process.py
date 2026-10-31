"""DNS, UDP transport and proxy testing diagnostics must report measured facts."""
from __future__ import annotations

import base64
import json
import socket

from huntx.core import remark_probe
from scripts import generate_site_data as site


def test_remark_tcp_measurement_never_probes_udp_declared_transports():
    vmess = {
        "add": "quic.example.com", "port": "443",
        "id": "11111111-2222-4333-8444-555555555555",
        "net": "quic", "tls": "tls",
    }
    encoded = base64.b64encode(json.dumps(vmess).encode("utf-8")).decode("ascii")
    for uri in (
        "vmess://" + encoded,
        "vless://11111111-2222-4333-8444-555555555555@edge.example.com:443?type=quic&security=tls",
        "socks5://username:password@edge.example.com:1080?network=udp",
    ):
        assert remark_probe._endpoint(uri) is None


def test_private_dns_result_is_not_a_publicly_resolved_endpoint(monkeypatch):
    def private_only(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ]
    monkeypatch.setattr(site.socket, "getaddrinfo", private_only)
    result = site.annotate_dns_resolution([
        {"server": "private.example", "port": 443},
    ])
    assert result[0]["dns_resolution"] == "non_public_dns_answer"


def test_ipv6_only_global_answer_is_valid_dns_evidence(monkeypatch):
    monkeypatch.setattr(site.socket, "getaddrinfo", lambda *_a, **_kw: [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
    ])
    result = site.annotate_dns_resolution([
        {"server": "ipv6.example", "port": 443},
    ])
    assert result[0]["dns_resolution"] == "resolved_from_publish_vantage"


def test_dns_resolution_failure_is_not_a_permanent_proxy_death(monkeypatch):
    def unavailable(*_a, **_kw):
        raise socket.gaierror("temporary name resolution failure")
    monkeypatch.setattr(site.socket, "getaddrinfo", unavailable)
    result = site.annotate_dns_resolution([{"server": "retry.example", "port": 443}])
    assert result[0]["dns_resolution"] == "unresolved_from_publish_vantage"
    assert result[0]["server"] == "retry.example"


def test_remark_probe_reports_nonpublic_dns_without_connecting(monkeypatch):
    calls = []
    monkeypatch.setattr(remark_probe.socket, "getaddrinfo", lambda *_a, **_kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    monkeypatch.setattr(remark_probe.socket, "socket", lambda *_a, **_kw: calls.append(True))
    _target, evidence = remark_probe._measure(("private.example", 443))
    assert evidence["dns_status"] == "non_public_answer"
    assert "probe_kind" not in evidence
    assert calls == []
