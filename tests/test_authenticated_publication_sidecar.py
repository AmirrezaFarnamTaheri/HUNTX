"""Authenticated production evidence must survive into published telemetry.

The sidecar contains only a canonical identity digest and timestamped probe
facts; never publish original userinfo, source tokens or raw share URIs.
"""
from __future__ import annotations

import hashlib
import json
import time

from huntx.formats.npvt import NpvtHandler, canonical_proxy_identity
from scripts import generate_site_data as site
from scripts.verify_dashboard_telemetry import validate_proxy_telemetry


def test_authenticated_health_sidecar_preserves_measurement_without_credentials(
    monkeypatch,
):
    now = time.time()
    link = "trojan://SUPER_SECRET@5.5.5.5:443?security=tls#Old"
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setattr("huntx.core.proxy_health.verified_records", lambda records: [
        {"data": {"line": link, "probe_kind": "protocol_authenticated",
                  "probe_authenticated": True,
                  "probe_checked_at": now, "probe_expires_at": now + 300,
                  "latency_ms": 91}}
    ])
    handler = NpvtHandler()
    built = handler.build([{"data": {"line": link}}])
    report = json.loads(handler.publication_evidence_bytes())
    digest = hashlib.sha256(
        canonical_proxy_identity(link).encode("utf-8")
    ).hexdigest()
    assert "trojan://" in built.decode("utf-8")
    assert report["schema_version"] == 1
    assert report["admitted_count"] == 1
    assert report["records"][digest]["duration_ms"] == 91
    assert report["records"][digest]["checked_at"] == now
    assert "SUPER_SECRET" not in json.dumps(report)
    assert "5.5.5.5" not in json.dumps(report)


def test_dashboard_restores_authenticated_provenance_and_expiry(
    tmp_path, monkeypatch
):
    now = time.time()
    link = "trojan://secret@5.5.5.5:443?security=tls#Example"
    digest = hashlib.sha256(
        canonical_proxy_identity(link).encode("utf-8")
    ).hexdigest()
    (tmp_path / "all_sources.json").write_text(json.dumps({
        "total": 1, "entries": [{"protocol": "trojan", "address": "5.5.5.5",
                                "port": 443, "raw": link, "tag": "Example"}]
    }), encoding="utf-8")
    (tmp_path / "all_sources_health.json").write_text(json.dumps({
        "schema_version": 1, "admitted_count": 1,
        "records": {digest: {
            "checked_at": now, "expires_at": now + 300, "duration_ms": 90
        }}
    }), encoding="utf-8")
    monkeypatch.setattr(site, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", tmp_path / "no-dev")
    nodes = site.parse_production_proxies()
    assert len(nodes) == 1
    assert nodes[0]["probe_kind"] == "protocol_authenticated"
    assert nodes[0]["authenticated_probe_ok"] is True
    assert nodes[0]["authenticated_latency_ms"] == 90

    nodes[0]["probe_ok"] = False
    nodes[0]["latency"] = None
    site.grade_proxy_health(nodes)
    assert nodes[0]["health_evidence"] == "fresh_authenticated_protocol"
    assert nodes[0]["health_grade"] is not None
    assert validate_proxy_telemetry([{
        **nodes[0], "pca_score": 0.5, "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank"
    }])["verified"] == 1

    nodes[0]["authenticated_probe_expires_at"] = now - 10
    site.grade_proxy_health(nodes)
    assert nodes[0]["health_evidence"] == "expired_authenticated_protocol"
    assert nodes[0]["health_grade"] is None
    assert validate_proxy_telemetry([{
        **nodes[0], "pca_score": 0.5, "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank"
    }])["expired"] == 1
