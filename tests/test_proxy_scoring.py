import pytest
from huntx.core.scoring import ProxyScoringEngine


def test_score_proxy_calculates_quality_score():
    engine = ProxyScoringEngine()
    record = {
        "uri": "vless://example.com:443?type=ws",
        "latency_ms": 120.0,
        "historical_success_rate": 0.95,
        "protocol": "vless",
    }
    score = engine.score_proxy(record)
    assert 80.0 <= score <= 100.0
