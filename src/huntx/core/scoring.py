from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional


def _finite_metric(value: Any, *, default: float, minimum: float, maximum: float | None = None) -> float:
    """Coerce untrusted telemetry to a finite bounded float before scoring."""
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    parsed = max(minimum, parsed)
    return min(parsed, maximum) if maximum is not None else parsed


class ProxyScoringEngine:
    """Calculates adaptive multi-metric quality scores for proxy nodes."""

    # Protocol weights for transport security
    SECURITY_WEIGHTS = {
        "reality": 10.0,
        "tls": 8.0,
        "grpc": 8.0,
        "h2": 8.0,
        "ws": 5.0,
        "none": 0.0,
    }

    def calculate_health_score(
        self,
        latency_ms: float,
        speed_mbps: float = 0.0,
        packet_loss: float = 0.0,
        security_type: str = "none",
        carrier: Optional[str] = None,
        target_isp: Optional[str] = None,
        *,
        probe_kind: str = "unverified",
        probe_ok: bool | None = None,
        observation_age_seconds: float | None = None,
        max_probe_age_seconds: float = 3600.0,
    ) -> Dict[str, Any]:
        """Calculates carrier-aware health score matching Master Compendium §8 formula.

        Score = 40.0 + max(0, 25 - latency/4) + Sum(Ws) + min(15, speed_mbps * 3) + carrier_boost - penalties
        """
        # External telemetry can contain NaN, infinity, missing and negative
        # measurements. Normalize before both arithmetic and threshold checks.
        latency_ms = _finite_metric(latency_ms, default=0.0, minimum=0.0)
        speed_mbps = _finite_metric(speed_mbps, default=0.0, minimum=0.0)
        packet_loss = _finite_metric(packet_loss, default=0.0, minimum=0.0, maximum=100.0)
        security_type = security_type.lower() if isinstance(security_type, str) else "none"
        base_score = 40.0

        # 1. Latency component
        latency_score = 0.0
        if latency_ms > 0:
            latency_score = max(0.0, 25.0 - (latency_ms / 4.0))

        # 2. Security weight
        sec_weight = self.SECURITY_WEIGHTS.get(security_type.lower(), 0.0)

        # 3. Speed component
        speed_score = min(15.0, speed_mbps * 3.0)

        # 4. Carrier alignment
        carrier_boost = 0.0
        if isinstance(carrier, str) and isinstance(target_isp, str) and carrier.strip() and carrier.strip().lower() == target_isp.strip().lower():
            carrier_boost = 5.0

        # 5. Penalties
        penalties = 0.0
        if packet_loss > 5.0:
            penalties += packet_loss * 2.0
        if latency_ms > 500.0:
            penalties += 10.0

        total = base_score + latency_score + sec_weight + speed_score + carrier_boost - penalties
        clamped = max(0.0, min(100.0, total))

        # Grade assignment
        if clamped >= 90.0:
            grade = "A+"
        elif clamped >= 80.0:
            grade = "A"
        elif clamped >= 70.0:
            grade = "B"
        elif clamped >= 55.0:
            grade = "C"
        elif clamped >= 40.0:
            grade = "D"
        else:
            grade = "F"

        # TCP connection does not authenticate proxy protocol credentials.
        # Keep a numeric estimate, but never label it as verified/recommended.
        age = _finite_metric(observation_age_seconds, default=float("inf"), minimum=0.0)
        threshold = _finite_metric(
            max_probe_age_seconds, default=3600.0, minimum=1.0,
            maximum=7 * 24 * 3600,
        )
        authenticated = (
            probe_kind == "protocol_authenticated"
            and probe_ok is True
            and 0 <= age <= threshold
            and latency_ms > 0
        )
        if probe_kind == "protocol_authenticated" and probe_ok is False:
            return {
                "score": 0.0, "grade": "F", "verified_grade": "F",
                "recommended": False, "evidence": "failed_probe",
            }
        if probe_kind == "tcp_connect" and probe_ok is False:
            return {
                "score": 0.0, "grade": "F", "verified_grade": None,
                "recommended": False, "evidence": "tcp_connect_failed",
            }
        return {
            "score": round(clamped, 2),
            "grade": grade,
            "verified_grade": grade if authenticated else None,
            "recommended": authenticated and clamped >= 75.0,
            "evidence": (
                "fresh_authenticated_protocol"
                if authenticated else
                "tcp_connect_only" if probe_kind == "tcp_connect" and probe_ok is True
                else "stale_authenticated_probe"
                if probe_kind == "protocol_authenticated" and probe_ok is True
                else "unverified"
            ),
        }

    def score_proxy(self, record: Mapping[str, Any]) -> float:
        """Rank measured nodes without accidentally reviving rejected history."""
        lifecycle = str(record.get("lifecycle", record.get("status", ""))).lower()
        if (
            record.get("probe_ok") is False
            or record.get("is_active") in (False, 0)
            or lifecycle in {"dead", "retired", "revoked", "quarantined", "invalid"}
        ):
            return 0.0
        latency = _finite_metric(record.get("latency_ms", 9999.0), default=9999.0, minimum=0.0)
        success_rate = _finite_metric(
            record.get("historical_success_rate", 0.5),
            default=0.5,
            minimum=0.0,
            maximum=1.0,
        )

        # 1. Latency Score (0 to 50 pts)
        if latency <= 100:
            lat_score = 50.0
        elif latency <= 500:
            lat_score = 50.0 - ((latency - 100) / 400.0) * 25.0
        elif latency <= 1500:
            lat_score = 25.0 - ((latency - 500) / 1000.0) * 20.0
        else:
            lat_score = 0.0

        # 2. Historical Success Score (0 to 50 pts)
        hist_score = success_rate * 50.0

        return round(min(100.0, max(0.0, lat_score + hist_score)), 2)
