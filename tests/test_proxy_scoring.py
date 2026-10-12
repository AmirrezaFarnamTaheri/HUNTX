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


def test_blank_carrier_and_target_do_not_get_alignment_boost():
    engine = ProxyScoringEngine()
    empty = engine.calculate_health_score(
        latency_ms=100.0, speed_mbps=2.0, packet_loss=0.0,
        security_type="none", carrier="", target_isp="",
    )
    whitespace = engine.calculate_health_score(
        latency_ms=100.0, speed_mbps=2.0, packet_loss=0.0,
        security_type="none", carrier="  ", target_isp=" ",
    )
    missing = engine.calculate_health_score(
        latency_ms=100.0, speed_mbps=2.0, packet_loss=0.0,
        security_type="none", carrier=None, target_isp=None,
    )
    assert empty["score"] == missing["score"] == whitespace["score"]

def test_network_reachability_does_not_claim_authenticated_proxy_health():
    engine = ProxyScoringEngine()
    kwargs = dict(
        latency_ms=35.0, speed_mbps=15.0, security_type="reality",
        carrier="MCI", target_isp="MCI",
    )
    untested = engine.calculate_health_score(**kwargs)
    tcp = engine.calculate_health_score(
        **kwargs, probe_kind="tcp_connect", probe_ok=True,
        observation_age_seconds=0.0,
    )
    verified = engine.calculate_health_score(
        **kwargs, probe_kind="protocol_authenticated", probe_ok=True,
        observation_age_seconds=60.0,
    )
    assert untested["grade"] == tcp["grade"] == verified["grade"]
    assert not untested["recommended"] and untested["verified_grade"] is None
    assert not tcp["recommended"] and tcp["verified_grade"] is None
    assert tcp["evidence"] == "tcp_connect_only"
    assert verified["recommended"] and verified["verified_grade"] == verified["grade"]
    expired = engine.calculate_health_score(
        **kwargs, probe_kind="protocol_authenticated", probe_ok=True,
        observation_age_seconds=3601.0,
    )
    assert not expired["recommended"] and expired["verified_grade"] is None
    assert expired["evidence"] == "stale_authenticated_probe"
    failed = engine.calculate_health_score(
        **kwargs, probe_kind="protocol_authenticated", probe_ok=False,
    )
    assert failed["score"] == 0 and failed["verified_grade"] == "F"
