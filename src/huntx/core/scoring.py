import math
from typing import Any, Dict


class ProxyScoringEngine:
    """Calculates adaptive multi-metric quality scores for proxy nodes."""

    def score_proxy(self, record: Dict[str, Any]) -> float:
        """Calculate a bounded 0-100 score from latency and success history."""
        latency = record.get("latency_ms", 9999.0)
        success_rate = record.get("historical_success_rate", 0.5)

        if not isinstance(latency, (int, float)) or isinstance(latency, bool) or not math.isfinite(latency) or latency < 0:
            latency = 9999.0
        if not isinstance(success_rate, (int, float)) or isinstance(success_rate, bool) or not math.isfinite(success_rate):
            success_rate = 0.0
        success_rate = min(1.0, max(0.0, success_rate))

        if latency <= 100:
            lat_score = 50.0
        elif latency <= 500:
            lat_score = 50.0 - ((latency - 100) / 400.0) * 25.0
        elif latency <= 1500:
            lat_score = 25.0 - ((latency - 500) / 1000.0) * 20.0
        else:
            lat_score = 0.0

        return round(lat_score + success_rate * 50.0, 2)
