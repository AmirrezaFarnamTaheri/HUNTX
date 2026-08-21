"""OONI Network Interference & Censorship Anomaly Feed Bridge.

Authority:
    OONI (Open Observatory of Network Interference) Data Specifications: https://ooni.org/data/
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Set

class OONIAnomalyType(str, Enum):
    """Types of network interference detected by OONI observation probes."""
    SNI_BLOCKING = "sni_blocking"
    DNS_TAMPERING = "dns_tampering"
    HTTP_THROTTLING = "http_throttling"
    TCP_RESET = "tcp_reset"
    UNKNOWN = "unknown"

@dataclass
class NetworkInterferenceAlert:
    """Structured alert indicating active censorship or throttling on an endpoint/SNI."""
    anomaly_type: OONIAnomalyType
    probe_cc: str
    probe_asn: str
    target: str
    anomaly_rate: float
    is_critical: bool
    timestamp: str

class OONIAnomalyBridge:
    """Correlates global network interference observations with candidate proxy nodes."""

    def __init__(self, critical_threshold: float = 0.75):
        self.critical_threshold = critical_threshold
        self.blocked_targets_by_cc: Dict[str, Set[str]] = {}

    def ingest_anomalies(self, anomalies: List[Dict[str, Any]]) -> List[NetworkInterferenceAlert]:
        """Ingest raw OONI anomaly events and index affected targets."""
        alerts: List[NetworkInterferenceAlert] = []

        for item in anomalies:
            raw_type = item.get("anomaly_type", "unknown")
            try:
                atype = OONIAnomalyType(raw_type)
            except ValueError:
                atype = OONIAnomalyType.UNKNOWN

            probe_cc = str(item.get("probe_cc", "")).upper()
            target = str(item.get("target", "")).strip().lower()
            rate = float(item.get("anomaly_rate", 0.0))
            is_crit = rate >= self.critical_threshold

            alert = NetworkInterferenceAlert(
                anomaly_type=atype,
                probe_cc=probe_cc,
                probe_asn=str(item.get("probe_asn", "")),
                target=target,
                anomaly_rate=rate,
                is_critical=is_crit,
                timestamp=str(item.get("timestamp", ""))
            )
            alerts.append(alert)

            if is_crit and probe_cc and target:
                if probe_cc not in self.blocked_targets_by_cc:
                    self.blocked_targets_by_cc[probe_cc] = set()
                self.blocked_targets_by_cc[probe_cc].add(target)

        return alerts

    def is_node_at_risk(self, node: Dict[str, Any], probe_cc: str) -> bool:
        """Check if a proxy node utilizes an SNI or IP actively flagged as blocked."""
        cc = probe_cc.upper()
        if cc not in self.blocked_targets_by_cc:
            return False

        blocked = self.blocked_targets_by_cc[cc]
        server = str(node.get("server", "")).strip().lower()
        sni = str(node.get("sni", "")).strip().lower()

        if server in blocked or (sni and sni in blocked):
            return True
        return False
