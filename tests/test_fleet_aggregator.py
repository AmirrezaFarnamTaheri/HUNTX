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


def test_fleet_consensus_uses_one_observation_per_probe_and_exact_target():
    aggregator = VantageFleetAggregator(domestic_region="IR")
    observations = [
        ProbeObservation("p-us", "US", "target-1", 40.0, True),
        ProbeObservation("p-us", "US", "target-1", 40.0, True),
        ProbeObservation("p-other", "IR", "target-2", 0.0, False),
        ProbeObservation("p-ir", "IR", "target-1", 0.0, False),
        ProbeObservation("p-nan", "US", "target-1", float("nan"), True),
    ]
    verdict = aggregator.aggregate("target-1", observations)
    assert verdict.reporting_probes_count == 2
    assert verdict.consensus_reachability == 0.5
    assert verdict.is_geoblocked is True
    assert verdict.median_latency_ms == 40.0
    assert verdict.regional_latencies == {"US": 40.0}
    assert verdict.blocked_regions == ["IR"]


def test_fleet_region_latency_is_median_not_last_writer():
    aggregator = VantageFleetAggregator()
    observations = [
        ProbeObservation("first", "US", "node", 10.0, True),
        ProbeObservation("second", "US", "node", 100.0, True),
        ProbeObservation("third", "US", "node", 20.0, True),
    ]
    assert aggregator.aggregate("node", observations).regional_latencies["US"] == 20.0


def test_region_is_not_blocked_when_another_probe_succeeds():
    aggregator = VantageFleetAggregator(domestic_region="IR")
    observations = [
        ProbeObservation("ir-failed", "IR", "target", 0.0, False),
        ProbeObservation("ir-alive", "IR", "target", 25.0, True),
        ProbeObservation("us-alive", "US", "target", 60.0, True),
    ]
    verdict = aggregator.aggregate("target", observations)
    assert verdict.blocked_regions == []
    assert verdict.is_geoblocked is False
