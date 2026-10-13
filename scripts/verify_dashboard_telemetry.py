"""Validate generated dashboard telemetry without treating TCP as proxy health.

A successful TCP handshake proves socket reachability, not that the proxy
protocol authenticated or routed traffic. Only fresh authenticated protocol
evidence may yield a verified health grade. Release and dev CI use this same
contract to avoid weakening the producer's security model.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

_LATENCY_GRADES = frozenset({"A+", "A", "B+", "B", "C+", "C"})
_TCP_EVIDENCE = frozenset({"tcp_connect_only", "tcp_failed_from_publish_vantage"})


def load_dashboard_proxies(path: Path) -> list[dict]:
    """Read the generated SAMPLE_PROXIES export, not fixture/fallback arrays."""
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"SAMPLE_PROXIES\s*=\s*(\[.*?\]);\s*\n", raw, re.S)
    if match is None:
        raise ValueError(f"SAMPLE_PROXIES export missing from {path}")
    proxies = json.loads(match.group(1))
    if not isinstance(proxies, list) or not all(isinstance(p, dict) for p in proxies):
        raise ValueError(f"SAMPLE_PROXIES must be an array of objects in {path}")
    return proxies


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_proxy_telemetry(proxies: list[dict]) -> dict[str, int]:
    """Require complete telemetry without claiming unverified proxies healthy."""
    if not proxies:
        raise AssertionError("dashboard published zero proxies")
    counts = {
        "proxies": len(proxies), "tcp_only": 0, "tcp_failed": 0,
        "verified": 0, "auth_failed": 0, "scored": 0,
    }
    for index, proxy in enumerate(proxies):
        ident = proxy.get("id") or proxy.get("server") or f"index {index}"

        def invalid(message: str) -> None:
            raise AssertionError(f"proxy {ident}: {message}")

        if type(proxy.get("probe_ok")) is not bool:
            invalid("missing TCP measurement outcome (probe_ok)")
        if "health_grade" not in proxy or "latency_grade" not in proxy:
            invalid("missing explicit health/latency grade fields")
        if not isinstance(proxy.get("health_status"), str) or not proxy["health_status"].strip():
            invalid("missing health status")
        latency_grade = proxy["latency_grade"]
        if latency_grade is not None and latency_grade not in _LATENCY_GRADES:
            invalid("invalid TCP latency band")
        if proxy["probe_ok"] is True and latency_grade is None:
            invalid("successful TCP measurement lacks latency band")
        if proxy["probe_ok"] is False and latency_grade is not None:
            invalid("failed TCP measurement has a latency band")

        evidence = proxy.get("health_evidence")
        grade = proxy["health_grade"]
        if evidence in _TCP_EVIDENCE:
            if grade is not None:
                invalid("unverified TCP reachability cannot receive a proxy health grade")
            expected = (
                "tcp_connect_only" if proxy["probe_ok"] is True
                else "tcp_failed_from_publish_vantage"
            )
            if evidence != expected:
                invalid("TCP evidence contradicts the measurement outcome")
            if proxy.get("probe_kind") == "protocol_authenticated" and proxy.get("authenticated_probe_ok") is False:
                invalid("failed authenticated probe must be explicitly graded F")
            counts["tcp_only" if proxy["probe_ok"] else "tcp_failed"] += 1
        elif evidence == "fresh_authenticated_protocol":
            if grade not in _LATENCY_GRADES:
                invalid("fresh authenticated proxy lacks a verified grade")
            age = proxy.get("authenticated_probe_age_seconds")
            duration = proxy.get("authenticated_latency_ms")
            if (
                proxy.get("probe_kind") != "protocol_authenticated"
                or proxy.get("authenticated_probe_ok") is not True
                or not _finite_number(age) or not 0 <= age <= 3600
                or not _finite_number(duration) or duration < 0
            ):
                invalid("verified grade lacks fresh authenticated protocol evidence")
            counts["verified"] += 1
        elif evidence == "failed_authenticated_protocol":
            if (
                grade != "F"
                or proxy.get("probe_kind") != "protocol_authenticated"
                or proxy.get("authenticated_probe_ok") is not False
            ):
                invalid("failed authenticated probe must have grade F")
            counts["auth_failed"] += 1
        else:
            invalid(f"unknown or missing health evidence {evidence!r}")

        score = proxy.get("pca_score")
        if not _finite_number(score) or not 0 <= score <= 1:
            invalid("missing or invalid governed score (0.0 is valid)")
        version = proxy.get("pca_version")
        if type(version) is not int or version < 1:
            invalid("missing governed score version")
        if proxy.get("pca_evidence") != "publisher_tcp_reachability_candidate_rank":
            invalid("missing governed score provenance")
        counts["scored"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_js", type=Path, help="generated docs/assets/js/data.js")
    args = parser.parse_args()
    counts = validate_proxy_telemetry(load_dashboard_proxies(args.data_js))
    print("dashboard telemetry verified: " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
