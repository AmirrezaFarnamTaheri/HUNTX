# Tests for OONI Censorship & Anomaly Feed Bridge
# Authority: Open Observatory of Network Interference (OONI) Data Spec: https://ooni.org/data/
import pytest
from huntx.pipeline.ooni import OONIAnomalyBridge, OONIAnomalyType, NetworkInterferenceAlert

def test_ooni_anomaly_type_classification():
    assert OONIAnomalyType.SNI_BLOCKING.value == "sni_blocking"
    assert OONIAnomalyType.DNS_TAMPERING.value == "dns_tampering"
    assert OONIAnomalyType.HTTP_THROTTLING.value == "http_throttling"
    assert OONIAnomalyType.TCP_RESET.value == "tcp_reset"

def test_ooni_bridge_ingests_anomalies_and_flags_nodes():
    bridge = OONIAnomalyBridge()
    anomalies = [
        {
            "anomaly_type": "sni_blocking",
            "probe_cc": "IR",
            "probe_asn": "AS58224",
            "target": "speed.cloudflare.com",
            "anomaly_rate": 0.95,
            "timestamp": "2026-08-21T18:00:00Z"
        },
        {
            "anomaly_type": "tcp_reset",
            "probe_cc": "CN",
            "probe_asn": "AS4134",
            "target": "104.16.1.1",
            "anomaly_rate": 0.88,
            "timestamp": "2026-08-21T18:00:00Z"
        }
    ]
    alerts = bridge.ingest_anomalies(anomalies)
    assert len(alerts) == 2
    assert isinstance(alerts[0], NetworkInterferenceAlert)
    assert alerts[0].is_critical is True

    # Test node impact evaluation
    node_impacted = {
        "server": "1.1.1.1",
        "sni": "speed.cloudflare.com",
        "country": "IR"
    }
    assert bridge.is_node_at_risk(node_impacted, probe_cc="IR") is True

    node_safe = {
        "server": "8.8.8.8",
        "sni": "safe.example.com",
        "country": "DE"
    }
    assert bridge.is_node_at_risk(node_safe, probe_cc="IR") is False
