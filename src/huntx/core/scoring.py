from typing import Dict, Any


class ProxyScoringEngine:
    """Calculates adaptive multi-metric quality scores for proxy nodes."""

    def score_proxy(self, record: Dict[str, Any]) -> float:
        latency = record.get("latency_ms", 9999.0)
        success_rate = record.get("historical_success_rate", 0.5)

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
        hist_score = min(50.0, max(0.0, success_rate * 50.0))

        return round(lat_score + hist_score, 2)
