# Tests for Multi-Region Vantage Fleet Aggregator
# Authority: RIPE Atlas Multi-Vantage Reachability Scoring & RFC 2679
import pytest
from huntx.pipeline.fleet_aggregator import VantageFleetAggregator, ProbeObservation, FleetConsensusVerdict

def test_fleet_aggregator_consensus_all_alive():
    aggregator = VantageFleetAggregator()
    observations = [
        ProbeObservation(probe_id="p-us-east", region="US", target_id="node-1", latency_ms=45.0, is_alive=True),
        ProbeObservation(probe_id="p-eu-central", region="DE", target_id="node-1", latency_ms=65.0, is_alive=True),
        ProbeObservation(probe_id="p-ap-tokyo", region="JP", target_id="node-1", latency_ms=110.0, is_alive=True),
        ProbeObservation(probe_id="p-me-tehran", region="IR", target_id="node-1", latency_ms=85.0, is_alive=True),
    ]

    verdict = aggregator.aggregate("node-1", observations)
    assert isinstance(verdict, FleetConsensusVerdict)
    assert verdict.consensus_reachability == 1.0
    assert verdict.reporting_probes_count == 4
    assert verdict.median_latency_ms == 75.0
    assert verdict.is_geoblocked is False

def test_fleet_aggregator_detects_domestic_geoblock():
    aggregator = VantageFleetAggregator(domestic_region="IR")
    observations = [
        # Reachable internationally
        ProbeObservation(probe_id="p-us-east", region="US", target_id="node-2", latency_ms=50.0, is_alive=True),
        ProbeObservation(probe_id="p-eu-central", region="DE", target_id="node-2", latency_ms=60.0, is_alive=True),
        # Blocked domestically in Iran
        ProbeObservation(probe_id="p-me-tehran", region="IR", target_id="node-2", latency_ms=0.0, is_alive=False),
    ]

    verdict = aggregator.aggregate("node-2", observations)
    assert verdict.consensus_reachability == pytest.approx(0.666, rel=1e-2)
    assert verdict.is_geoblocked is True
    assert "IR" in verdict.blocked_regions
