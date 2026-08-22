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
    ) -> Dict[str, Any]:
        """Calculates carrier-aware health score matching Master Compendium §8 formula.

        Score = 40.0 + max(0, 25 - latency/4) + Sum(Ws) + min(15, speed_mbps * 3) + carrier_boost - penalties
        """
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
        if carrier and target_isp and carrier.strip().lower() == target_isp.strip().lower():
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

        return {
            "score": round(clamped, 2),
            "grade": grade,
            "recommended": clamped >= 75.0,
        }

    def score_proxy(self, record: Mapping[str, Any]) -> float:
        """Backward-compatible proxy score calculation."""
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
