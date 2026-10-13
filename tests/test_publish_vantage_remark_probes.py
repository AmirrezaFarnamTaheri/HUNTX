"""Publisher TCP/DNS label telemetry is safely bounded and never invented."""
from __future__ import annotations

import socket
import time
from urllib.parse import unquote, urlsplit

from huntx.core import remark_probe
from huntx.formats.npvt import NpvtHandler


def test_udp_protocols_are_never_described_as_tcp_probed():
    assert remark_probe._endpoint("hy2://pass@one.example:443?sni=other.example") is None
    assert remark_probe._endpoint("tuic://uuid:pass@one.example:443?sni=other.example") is None


def test_private_dns_addresses_are_never_connected(monkeypatch):
    calls = []
    monkeypatch.setattr(remark_probe.socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.3.4.5", 443)),
    ])
    monkeypatch.setattr(remark_probe.socket, "socket", lambda *a, **k: calls.append(a))
    target, observation = remark_probe._measure(("private.example", 443))
    assert target == ("private.example", 443)
    assert observation == {}
    assert calls == []


def test_real_public_dns_and_tcp_connect_are_labeled_without_auth_claim(monkeypatch):
    calls = []

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def settimeout(self, timeout):
            assert 0 < timeout <= 1.5
        def connect(self, destination):
            calls.append(destination)

    monkeypatch.setattr(remark_probe.socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))
    ])
    monkeypatch.setattr(remark_probe.socket, "socket", lambda *a, **k: Connection())
    target, evidence = remark_probe._measure(("public.example", 443))
    assert target == ("public.example", 443)
    assert calls == [("1.1.1.1", 443)]  # pinned public IP, never hostname
    assert evidence["dns_status"] == "resolved"
    assert evidence["probe_kind"] == "tcp_connect"
    assert evidence["probe_authenticated"] is False
    assert evidence["latency_ms"] >= 0
    assert evidence["probe_checked_at"] < evidence["probe_expires_at"]


def test_export_attaches_real_measurement_when_explicitly_enabled(monkeypatch):
    import huntx.core.remark_probe as probe
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    monkeypatch.setenv("HUNTX_REMARK_TCP_PROBE", "1")
    sample = "trojan://secret@node.example.com:443?type=ws&security=tls"
    now = time.time()
    seen = []
    def measured(uris):
        seen.extend(uris)
        return {sample: {
            "probe_kind": "tcp_connect", "probe_authenticated": False,
            "probe_checked_at": now, "probe_expires_at": now + 300,
            "latency_ms": 48,
            "dns_status": "resolved", "dns_checked_at": now,
            "dns_expires_at": now + 300,
        }}
    monkeypatch.setattr(probe, "probe_remark_evidence", measured)
    result = NpvtHandler().build([{"data": {"line": sample}}]).decode()
    label = unquote(urlsplit(result).fragment)
    assert seen == [sample]
    assert "DNS:OK" in label and "TCP:48ms" in label
    assert "AUTH" not in label and "DL:" not in label


def test_export_uses_no_network_without_explicit_opt_in(monkeypatch):
    import huntx.core.remark_probe as probe
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    monkeypatch.delenv("HUNTX_REMARK_TCP_PROBE", raising=False)
    monkeypatch.setattr(probe, "probe_remark_evidence", lambda *a: (_ for _ in ()).throw(AssertionError("must not probe")))
    sample = "trojan://secret@node.example.com:443?type=ws&security=tls"
    result = NpvtHandler().build([{"data": {"line": sample}}]).decode()
    label = unquote(urlsplit(result).fragment)
    assert "TROJAN-WS" in label
    assert "ZZ" not in label
    assert "TCP:" not in label
