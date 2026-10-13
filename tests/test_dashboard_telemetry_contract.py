"""Regression tests for evidence-aware generated dashboard telemetry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_dashboard_telemetry import (
    load_dashboard_proxies,
    validate_proxy_telemetry,
)


def _proxy(**changes: object) -> dict:
    """Representative publisher TCP measurement, not a verified proxy."""
    item = {
        "id": "px-0001",
        "probe_ok": True,
        "latency": 22,
        "latency_grade": "A+",
        "health_grade": None,
        "health_evidence": "tcp_connect_only",
        "health_status": "TCP reachable; proxy protocol unverified",
        "pca_score": 0.74,
        "pca_version": 1,
        "pca_evidence": "publisher_tcp_reachability_candidate_rank",
    }
    item.update(changes)
    return item


def test_tcp_reachability_is_measured_but_never_a_verified_health_grade() -> None:
    result = validate_proxy_telemetry([_proxy()])
    assert result["tcp_only"] == 1
    assert result["verified"] == 0
    assert result["scored"] == 1


def test_failed_tcp_probe_has_explicit_evidence_but_no_health_grade() -> None:
    result = validate_proxy_telemetry([
        _proxy(probe_ok=False, latency=None, latency_grade=None,
               health_evidence="tcp_failed_from_publish_vantage")
    ])
    assert result["tcp_failed"] == 1


def test_fresh_authenticated_success_can_be_graded() -> None:
    result = validate_proxy_telemetry([
        _proxy(probe_kind="protocol_authenticated", authenticated_probe_ok=True,
               authenticated_probe_age_seconds=59,
               authenticated_latency_ms=33, health_grade="A",
               health_evidence="fresh_authenticated_protocol")
    ])
    assert result["verified"] == 1


def test_failed_authenticated_protocol_is_grade_f_even_with_tcp_success() -> None:
    result = validate_proxy_telemetry([
        _proxy(probe_kind="protocol_authenticated", authenticated_probe_ok=False,
               health_grade="F", health_evidence="failed_authenticated_protocol")
    ])
    assert result["auth_failed"] == 1


@pytest.mark.parametrize("changes,pattern", [
    ({"health_grade": "A+"}, "unverified TCP.*health grade"),
    ({"health_grade": "F"}, "unverified TCP.*health grade"),
    ({"health_evidence": "fresh_authenticated_protocol", "health_grade": "A"},
     "lacks fresh authenticated"),
    ({"probe_ok": None}, "missing TCP measurement"),
    ({"probe_ok": False, "latency_grade": "A+"}, "failed TCP"),
    ({"health_evidence": "unmeasured"}, "unknown or missing health evidence"),
    ({"pca_score": None}, "governed score"),
    ({"pca_score": 1.5}, "governed score"),
    ({"pca_score": float("nan")}, "governed score"),
    ({"pca_version": None}, "governed score version"),
    ({"pca_evidence": None}, "governed score provenance"),
    ({"health_status": ""}, "health status"),
])
def test_invalid_telemetry_is_rejected(changes: dict, pattern: str) -> None:
    with pytest.raises(AssertionError, match=pattern):
        validate_proxy_telemetry([_proxy(**changes)])


def test_stale_authenticated_probe_does_not_qualify_for_verified_grade() -> None:
    with pytest.raises(AssertionError, match="lacks fresh authenticated"):
        validate_proxy_telemetry([
            _proxy(probe_kind="protocol_authenticated", authenticated_probe_ok=True,
                   authenticated_probe_age_seconds=3601,
                   authenticated_latency_ms=33, health_grade="B",
                   health_evidence="fresh_authenticated_protocol")
        ])


def test_zero_pca_score_is_a_valid_governed_score() -> None:
    assert validate_proxy_telemetry([_proxy(pca_score=0.0)])["scored"] == 1


def test_empty_output_is_rejected() -> None:
    with pytest.raises(AssertionError, match="zero proxies"):
        validate_proxy_telemetry([])


def test_dashboard_loader_reads_the_export_not_unrelated_arrays(tmp_path: Path) -> None:
    data_js = tmp_path / "data.js"
    data_js.write_text(
        "export const FALLBACK_CATALOG = [1,2];\n"
        + "export const SAMPLE_PROXIES = " + json.dumps([_proxy()]) + ";\n"
        + "export const INGEST_STATS = {};\n", encoding="utf-8"
    )
    assert load_dashboard_proxies(data_js)[0]["id"] == "px-0001"


def test_dashboard_loader_rejects_missing_export(tmp_path: Path) -> None:
    data_js = tmp_path / "data.js"
    data_js.write_text("export const INGEST_STATS = {};\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SAMPLE_PROXIES export missing"):
        load_dashboard_proxies(data_js)
