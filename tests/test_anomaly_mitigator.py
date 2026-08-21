# Tests for Statistical Anomaly Detector & Auto-Mitigation Circuit Breaker
# Authority: NIST SP 800-137, Welford Online Variance Method
import pytest
from huntx.pipeline.anomaly_mitigator import AnomalyMitigator, NodeHealthState

def test_anomaly_mitigator_initial_healthy_state():
    mitigator = AnomalyMitigator(z_threshold=2.5, consecutive_spikes_to_trip=2)
    # Feed stable baseline observations (50ms +- 2ms)
    for _ in range(20):
        state = mitigator.observe("node-1", latency_ms=50.0)
        assert state == NodeHealthState.HEALTHY

def test_anomaly_mitigator_quarantines_on_sudden_latency_spike():
    mitigator = AnomalyMitigator(z_threshold=2.5, consecutive_spikes_to_trip=2)
    # 1. Warm up baseline
    for _ in range(30):
        mitigator.observe("node-1", latency_ms=40.0)

    # 2. First severe spike (400ms -> z > 5)
    s1 = mitigator.observe("node-1", latency_ms=400.0)
    assert s1 == NodeHealthState.SUSPECT

    # 3. Second severe spike -> trips into QUARANTINED
    s2 = mitigator.observe("node-1", latency_ms=450.0)
    assert s2 == NodeHealthState.QUARANTINED
    assert mitigator.is_available("node-1") is False

def test_anomaly_mitigator_probation_and_recovery():
    mitigator = AnomalyMitigator(z_threshold=2.5, consecutive_spikes_to_trip=1)
    for _ in range(20):
        mitigator.observe("node-1", latency_ms=40.0)

    # Trip
    mitigator.observe("node-1", latency_ms=500.0)
    assert mitigator.get_state("node-1") == NodeHealthState.QUARANTINED

    # Attempt recovery probe
    mitigator.enter_probation("node-1")
    assert mitigator.get_state("node-1") == NodeHealthState.PROBATION

    # Feed healthy observations in probation -> restores to HEALTHY
    mitigator.observe("node-1", latency_ms=42.0)
    mitigator.observe("node-1", latency_ms=41.0)
    assert mitigator.get_state("node-1") == NodeHealthState.HEALTHY
