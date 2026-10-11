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


def test_health_scoring_rejects_non_finite_and_negative_telemetry():
    import math

    engine = ProxyScoringEngine()
    baseline = engine.calculate_health_score(
        latency_ms=0.0, speed_mbps=0.0, packet_loss=0.0, security_type="none"
    )
    for metric in (float("nan"), float("inf"), -42.0, None, "invalid"):
        score = engine.calculate_health_score(
            latency_ms=metric, speed_mbps=metric, packet_loss=metric,
            security_type=None, carrier=None, target_isp=12,
        )
        assert score == baseline
        assert math.isfinite(score["score"])
        assert 0 <= score["score"] <= 100
