"""UDP/QUIC nodes are not TCP-dead; native authentication is distinct evidence."""
from __future__ import annotations

import time

import pytest

from scripts import generate_site_data as site
from scripts.verify_dashboard_telemetry import validate_proxy_telemetry


@pytest.mark.parametrize(("protocol", "transport"), [
    ("hysteria2", "tcp"), ("hy2", "tcp"), ("hysteria", "tcp"),
    ("tuic", "tcp"), ("wireguard", "tcp"),
    ("vmess", "quic"), ("vless", "quic"), ("socks", "udp"),
])
def test_udp_proxy_is_not_falsely_scored_by_tcp_probe(monkeypatch, protocol, transport):
    def illegal_network_call(*_args, **_kw):
        raise AssertionError("native UDP proxy must not trigger a TCP connection")
    monkeypatch.setattr(site.socket, "getaddrinfo", illegal_network_call)
    monkeypatch.setattr(site.socket, "socket", illegal_network_call)
    item = {"protocol": protocol, "transport": transport, "server": "edge.example.net", "port": 443}
    nodes = site.probe_tcp_latency([item])
    assert nodes[0]["probe_transport"] == "udp"
    assert nodes[0]["probe_ok"] is None
    assert nodes[0].get("latency") is None
    graded = site.grade_proxy_health(nodes)
    assert graded[0]["health_evidence"] == "udp_native_handshake_unmeasured"
    assert graded[0]["health_grade"] is None
    assert "TCP unreachable" not in graded[0]["health_status"]


def test_native_udp_with_fresh_authenticated_https_evidence_is_not_dead():
    now = time.time()
    node = {
        "protocol": "hysteria2", "transport": "tcp", "server": "edge.example.net",
        "port": 443, "probe_transport": "udp", "probe_ok": None,
        "probe_kind": "protocol_authenticated",
        "authenticated_probe_ok": True, "authenticated_probe_age_seconds": 5,
        "authenticated_latency_ms": 32, "authenticated_probe_expires_at": now + 200,
        "security_grade": "A", "geo_verified": False,
    }
    graded = site.grade_proxy_health([node])
    assert graded[0]["health_evidence"] == "fresh_authenticated_protocol"
    assert graded[0]["health_grade"] is not None
    ranked = site.score_governed_pca(graded)
    assert ranked[0]["pca_score"] >= 0.4
    assert ranked[0]["pca_evidence"] == "publisher_tcp_reachability_candidate_rank"


def test_native_udp_unmeasured_telemetry_is_not_fabricated_tcp_failure():
    node = {
        "id": "synthetic-udp", "protocol": "hysteria2",
        "probe_transport": "udp", "probe_ok": None, "latency": None,
        "latency_grade": None, "health_grade": None,
        "health_status": "Native UDP proxy handshake not measured",
        "health_evidence": "udp_native_handshake_unmeasured",
        "pca_score": 0.0, "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank",
    }
    counts = validate_proxy_telemetry([node])
    assert counts["udp_unmeasured"] == 1
    assert counts["tcp_failed"] == 0


def test_only_authenticated_failure_receives_failed_proxy_grade():
    node = {
        "protocol": "vless", "transport": "ws",
        "server": "edge.example.net", "port": 443,
        "probe_ok": True, "latency": 4,
        "probe_kind": "protocol_authenticated", "authenticated_probe_ok": False,
    }
    result = site.grade_proxy_health([node])[0]
    assert result["health_grade"] == "F"
    assert result["health_evidence"] == "failed_authenticated_protocol"
