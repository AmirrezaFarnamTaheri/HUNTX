"""Multi-Region Vantage Fleet Telemetry Aggregator.

Authority:
    RIPE Atlas Multi-Vantage Global Measurement Methodologies: https://atlas.ripe.net/docs/
    RFC 2679 (A One-Way Delay Metric for IPPM): https://datatracker.ietf.org/doc/html/rfc2679
"""
import statistics
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ProbeObservation:
    """Telemetry report from an individual edge vantage probe."""
    probe_id: str
    region: str
    target_id: str
    latency_ms: float
    is_alive: bool


@dataclass
class FleetConsensusVerdict:
    """Consensus verdict derived from multi-region probe observations."""
    target_id: str
    consensus_reachability: float
    reporting_probes_count: int
    median_latency_ms: float
    is_geoblocked: bool
    blocked_regions: List[str] = field(default_factory=list)
    regional_latencies: Dict[str, float] = field(default_factory=dict)


class VantageFleetAggregator:
    """Aggregates distributed probe observations to produce consensus health scores."""

    def __init__(self, domestic_region: str = "IR"):
        self.domestic_region = domestic_region.upper()

    def aggregate(self, target_id: str, observations: List[ProbeObservation]) -> FleetConsensusVerdict:
        """Calculate multi-region reachability consensus, median latency, and geoblocking flags."""
        if not observations:
            return FleetConsensusVerdict(
                target_id=target_id,
                consensus_reachability=0.0,
                reporting_probes_count=0,
                median_latency_ms=0.0,
                is_geoblocked=False
            )

        alive_count = 0
        latencies: List[float] = []
        regional_latencies: Dict[str, float] = {}
        blocked_regions: List[str] = []
        alive_non_domestic = False
        domestic_observations = 0
        dead_in_domestic = 0
        alive_in_domestic = 0

        for obs in observations:
            region = obs.region.upper()
            if obs.is_alive:
                alive_count += 1
                latencies.append(obs.latency_ms)
                regional_latencies[region] = obs.latency_ms
                if region != self.domestic_region:
                    alive_non_domestic = True
                else:
                    domestic_observations += 1
                    alive_in_domestic += 1
            else:
                blocked_regions.append(region)
                if region == self.domestic_region:
                    domestic_observations += 1
                    dead_in_domestic += 1

        total_probes = len(observations)
        reachability_ratio = alive_count / total_probes if total_probes > 0 else 0.0
        median_lat = float(statistics.median(latencies)) if latencies else 0.0

        # Geoblocking heuristic: Alive internationally but unreachable domestically
        is_geoblocked = alive_non_domestic and domestic_observations > 0 and dead_in_domestic == domestic_observations and alive_in_domestic == 0

        return FleetConsensusVerdict(
            target_id=target_id,
            consensus_reachability=reachability_ratio,
            reporting_probes_count=total_probes,
            median_latency_ms=median_lat,
            is_geoblocked=is_geoblocked,
            blocked_regions=blocked_regions,
            regional_latencies=regional_latencies
        )
