"""Never call an unauditable or expired proxy check a fresh authenticated success."""
from __future__ import annotations

import math
import time

import pytest

from scripts.generate_site_data import grade_proxy_health
from scripts.verify_dashboard_telemetry import validate_proxy_telemetry


def _auth_node(**changes):
    item = {
        "id": "fixture",
        "protocol": "trojan",
        "server": "edge.example.invalid", "port": 443,
        "probe_transport": "tcp", "probe_ok": True, "latency": 22,
        "probe_kind": "protocol_authenticated", "authenticated_probe_ok": True,
        "authenticated_probe_age_seconds": 1,
        "authenticated_latency_ms": 30,
        "security_grade": "A", "geo_verified": False,
    }
    item.update(changes)
    return item


@pytest.mark.parametrize("expiry", [None, False, 0, float("nan"), float("inf"), "2099-01-01"])
def test_unauditable_expiry_never_becomes_verified_proxy_health(expiry):
    item = _auth_node(authenticated_probe_expires_at=expiry)
    result = grade_proxy_health([item])[0]
    assert result["health_evidence"] != "fresh_authenticated_protocol"
    assert result["health_grade"] is None


def test_expired_verified_https_is_not_mislabeled_fresh():
    item = _auth_node(authenticated_probe_expires_at=time.time() - 1)
    result = grade_proxy_health([item])[0]
    assert result["health_evidence"] == "expired_authenticated_protocol"
    assert result["health_grade"] is None


def test_future_expiry_and_fresh_authenticated_proof_still_grades():
    item = _auth_node(authenticated_probe_expires_at=time.time() + 300)
    result = grade_proxy_health([item])[0]
    assert result["health_evidence"] == "fresh_authenticated_protocol"
    assert result["health_grade"] is not None


def _telemetry(**changes):
    item = grade_proxy_health([
        _auth_node(authenticated_probe_expires_at=time.time() + 300)
    ])[0]
    item.update({
        "latency_grade": "A+",
        "pca_score": 0.7,
        "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank",
    })
    item.update(changes)
    return item


@pytest.mark.parametrize("expiry", [None, False, 0, float("nan"), float("inf"), "bad"])
def test_dashboard_telemetry_rejects_fabricated_freshness(expiry):
    with pytest.raises(AssertionError, match="lacks fresh authenticated"):
        validate_proxy_telemetry([_telemetry(authenticated_probe_expires_at=expiry)])


def test_dashboard_telemetry_accepts_really_fresh_authenticated_https():
    counts = validate_proxy_telemetry([_telemetry()])
    assert counts["verified"] == 1
    assert counts["tcp_failed"] == 0


def test_native_udp_unmeasured_cannot_claim_tcp_failed_in_telemetry():
    item = {
        "id": "fixture-udp",
        "protocol": "hysteria2",
        "probe_transport": "udp", "probe_ok": False,
        "latency": None, "latency_grade": None,
        "health_grade": None,
        "health_evidence": "tcp_failed_from_publish_vantage",
        "health_status": "TCP unreachable",
        "pca_score": 0.0, "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank",
    }
    with pytest.raises(AssertionError, match="native UDP.*TCP"):
        validate_proxy_telemetry([item])
