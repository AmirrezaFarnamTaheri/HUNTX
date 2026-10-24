"""Every HTTPS gate candidate receives one explicit, credential-safe disposition."""
import json
import time

from huntx.core import proxy_health
from huntx.formats.npvt import NpvtHandler


def test_health_gate_distinguishes_failure_invalid_and_admitted(monkeypatch):
    now = time.time()
    monkeypatch.setattr(proxy_health.shutil, "which", lambda _: "/bin/sing-box")
    monkeypatch.setattr(proxy_health, "_verify_engine", lambda _: None)
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "2")
    uris = [
        "trojan://alpha@5.5.5.5:443?security=tls#One",
        "trojan://beta@5.5.5.6:443?security=tls#Two",
        "trojan://gamma@5.5.5.7:443?security=tls#Three",
    ]

    def fake_probe(uri: str, _binary: str, *, timeout: float):
        if "alpha" in uri:
            return {"ok": True, "latency_ms": 45, "checked_at": now,
                    "reason": "authenticated_https"}
        if "beta" in uri:
            return {"ok": True, "latency_ms": float("nan"),
                    "checked_at": now, "reason": "authenticated_https"}
        return {"ok": False, "reason": "https_path_failed"}

    monkeypatch.setattr(proxy_health, "check_proxy", fake_probe)
    handler = NpvtHandler()
    payload = handler.build([{"data": {"line": uri}} for uri in uris])
    assert payload.decode().count("trojan://") == 1
    gate = json.loads(handler.publication_gate_bytes())
    assert gate["candidates"] == 3
    assert gate["admitted"] == 1
    assert gate["rejected"] == 2
    assert gate["reasons"] == {
        "admitted": 1, "invalid_measurement": 1, "https_path_failed": 1,
    }
    assert len(gate["identities"]) == 3
    assert "alpha@" not in json.dumps(gate)
    assert "beta@" not in json.dumps(gate)
    assert "gamma@" not in json.dumps(gate)
