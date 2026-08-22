"""Vantage Probe Cluster Connector.

Authority:
    RFC 7231 (HTTP/1.1 Semantics): https://datatracker.ietf.org/doc/html/rfc7231
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import math

@dataclass
class VantageProbeObservation:
    """Individual measurement from a distributed edge vantage agent."""
    region_id: str
    provider: str
    target: str
    alive: bool
    latency_ms: float
    protocol: Optional[str]
    timestamp: str

class VantageProbeConnector:
    """Ingests multi-region vantage telemetry matrices into HUNTX."""

    def parse_report(self, payload: Dict[str, Any]) -> List[VantageProbeObservation]:
        """Parse raw vantage JSON report into structured observation records."""
        if not payload or not isinstance(payload, dict):
            return []

        region_id = payload.get("region_id")
        provider = payload.get("provider", "generic")
        timestamp = payload.get("timestamp", "")
        observations_raw = payload.get("observations")

        if not region_id or not isinstance(observations_raw, list):
            return []

        results: List[VantageProbeObservation] = []
        for obs in observations_raw:
            if not isinstance(obs, dict):
                continue
            target = obs.get("target")
            if not target:
                continue
            alive = obs.get("alive")
            if not isinstance(alive, bool):
                continue
            if not isinstance(target, str) or not target.strip():
                continue
            try:
                latency_ms = float(obs.get("latency_ms", 0.0))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(latency_ms) or latency_ms < 0:
                continue
            results.append(VantageProbeObservation(
                region_id=region_id,
                provider=provider,
                target=target,
                alive=alive,
                latency_ms=latency_ms,
                protocol=obs.get("protocol"),
                timestamp=timestamp
            ))

        return results
