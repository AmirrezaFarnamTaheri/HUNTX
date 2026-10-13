"""Regression contracts for compact, honest, cross-client remark tags."""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import unquote, urlsplit

from huntx.formats.npvt import add_clean_remark, format_evidence_remark

URI = "vless://11111111-2222-3333-4444-555555555555@edge.example.com:443?security=tls&type=ws#DE"


def test_terminal_identity_survives_extremely_long_metadata(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    monkeypatch.setattr("huntx.formats.npvt.time.time", lambda: 1800000100)
    metadata = {
        "endpoint": {
            "intelligence": {"status": "matched", "expires_at": 1800003600},
            "geo": {"status": "prefix_dataset_estimate", "country_code": "DE"},
            "asn": 13335,
            "cdn_provider": "Extremely Long Provider Name Repeated Repeated Repeated",
        },
        "probe_kind": "tcp_connect", "probe_checked_at": 1800000000,
        "probe_expires_at": 1800002000, "latency_ms": 12.25,
    }
    tag = format_evidence_remark(URI, metadata)
    assert tag.startswith("🇩🇪 DE | VLESS-WS-TLS")
    assert "AS13335" in tag and "TCP:12ms" in tag
    assert len(tag) <= 110
    assert re.search(r" [|] [0-9a-f]{10}$", tag)
    assert tag == format_evidence_remark(URI, metadata)


def test_insecure_tls_configuration_is_visibly_disclosed_in_remark(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    raw = URI.replace("?security=tls", "?security=tls&allowInsecure=1")
    remark = unquote(urlsplit(add_clean_remark(raw, {})).fragment)
    assert "UNSAFE" in remark
    assert "✔" not in remark and "⭐" not in remark


def test_authentication_claim_requires_fresh_explicit_protocol_evidence(monkeypatch):
    monkeypatch.setattr("huntx.formats.npvt.time.time", lambda: 1800000100)
    unknown = {"probe_kind": "protocol_authenticated", "probe_authenticated": True,
               "latency_ms": 25, "probe_checked_at": 1, "probe_expires_at": 2}
    assert "AUTH:" not in format_evidence_remark(URI, unknown)
    fresh = {**unknown, "probe_checked_at": 1800000000, "probe_expires_at": 1800000300}
    assert "AUTH:25ms" in format_evidence_remark(URI, fresh)
    assert "Verified" not in format_evidence_remark(URI, fresh)


def test_vmess_decoding_still_preserves_credentials_and_config(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    obj = {"v": "2", "ps": "old", "add": "edge.example.com", "port": "443",
           "id": "11111111-2222-3333-4444-555555555555", "net": "ws", "tls": "tls"}
    uri = "vmess://" + base64.b64encode(json.dumps(obj).encode()).decode()
    tagged = add_clean_remark(uri, {})
    decoded = json.loads(base64.b64decode(tagged[8:] + "=" * (-len(tagged[8:]) % 4)))
    assert decoded["id"] == obj["id"]
    assert decoded["add"] == obj["add"]
    assert "VMESS" in decoded["ps"]
    assert re.search(r"[0-9a-f]{10}$", decoded["ps"])
