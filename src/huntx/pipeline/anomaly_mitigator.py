"""Statistical Latency Anomaly Detector & Auto-Mitigation Circuit Breaker.

Authority:
    NIST SP 800-137: Information Security Continuous Monitoring (ISCM).
    Welford, B. P. (1962): Note on a method for calculating corrected sums of squares and products.
"""
import math
from enum import Enum
from dataclasses import dataclass
from typing import Dict

class NodeHealthState(str, Enum):
    """Health classification and circuit breaker states."""
    HEALTHY = "healthy"
    SUSPECT = "suspect"
    QUARANTINED = "quarantined"
    PROBATION = "probation"

@dataclass
class NodeTelemetryBaseline:
    """Welford accumulator for streaming mean and variance estimation."""
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    spike_count: int = 0
    probation_successes: int = 0
    state: NodeHealthState = NodeHealthState.HEALTHY

    def update(self, x: float) -> None:
        """Update online mean and M2 sum of squared differences."""
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def variance(self) -> float:
        """Sample variance."""
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def std_dev(self) -> float:
        """Standard deviation with a non-zero floor."""
        return math.sqrt(max(1.0, self.variance))

class AnomalyMitigator:
    """Detects statistical latency anomalies and executes automated circuit-breaker quarantine."""

    def __init__(
        self,
        z_threshold: float = 2.5,
        consecutive_spikes_to_trip: int = 2,
        min_warmup_samples: int = 10
    ):
        self.z_threshold = z_threshold
        self.consecutive_spikes_to_trip = consecutive_spikes_to_trip
        self.min_warmup_samples = min_warmup_samples
        self.nodes: Dict[str, NodeTelemetryBaseline] = {}

    def _get_node(self, node_id: str) -> NodeTelemetryBaseline:
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeTelemetryBaseline()
        return self.nodes[node_id]

    def get_state(self, node_id: str) -> NodeHealthState:
        """Get current health state for a node."""
        return self._get_node(node_id).state

    def is_available(self, node_id: str) -> bool:
        """Check if node is eligible for proxy routing."""
        return self.get_state(node_id) != NodeHealthState.QUARANTINED

    def enter_probation(self, node_id: str) -> None:
        """Move quarantined node to probation to test recovery."""
        node = self._get_node(node_id)
        node.state = NodeHealthState.PROBATION
        node.probation_successes = 0
        node.spike_count = 0

    def observe(self, node_id: str, latency_ms: float) -> NodeHealthState:
        """Process incoming latency measurement and update state machine."""
        node = self._get_node(node_id)

        # Warmup phase: establish initial statistical distribution
        if node.count < self.min_warmup_samples:
            node.update(latency_ms)
            node.state = NodeHealthState.HEALTHY
            return node.state

        # Compute Z-score against running baseline
        z_score = (latency_ms - node.mean) / node.std_dev

        if z_score > self.z_threshold:
            node.spike_count += 1
            node.probation_successes = 0
            if node.spike_count >= self.consecutive_spikes_to_trip:
                node.state = NodeHealthState.QUARANTINED
            else:
                node.state = NodeHealthState.SUSPECT
        else:
            # Healthy sample
            node.spike_count = 0
            if node.state == NodeHealthState.PROBATION:
                node.probation_successes += 1
                if node.probation_successes >= 2:
                    node.state = NodeHealthState.HEALTHY
            elif node.state == NodeHealthState.SUSPECT:
                node.state = NodeHealthState.HEALTHY

            # Only incorporate non-anomalous samples into running distribution
            node.update(latency_ms)

        return node.state
