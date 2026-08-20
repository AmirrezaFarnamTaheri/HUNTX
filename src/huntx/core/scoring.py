from __future__ import annotations

import math
from typing import Any, Mapping


def _finite_metric(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float | None = None,
) -> float:
    """Coerce an untrusted metric to a finite bounded float."""
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


class ProxyScoringEngine:
    """Calculate a stable 0..100 quality score from bounded proxy metrics."""

    def score_proxy(self, record: Mapping[str, Any]) -> float:
        """Score one record without allowing malformed telemetry to poison ranking."""
        latency = _finite_metric(
            record.get("latency_ms", 9999.0),
            default=9999.0,
            minimum=0.0,
        )
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
