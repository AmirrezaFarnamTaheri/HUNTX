# Tests for Vantage Probe Cluster Connector (Python Plane)
from huntx.connectors.vantage_probe import VantageProbeConnector, VantageProbeObservation


def test_vantage_connector_ingests_reports():
    connector = VantageProbeConnector()
    sample_payload = {
        "region_id": "ap-southeast-sin",
        "provider": "aws",
        "timestamp": "2026-08-21T18:00:00Z",
        "observations": [
            {"target": "104.16.1.1:443", "alive": True, "latency_ms": 12.4, "protocol": "vless"},
            {"target": "185.1.1.1:443", "alive": False, "latency_ms": 0.0, "protocol": "trojan"}
        ]
    }
    obs = connector.parse_report(sample_payload)
    assert len(obs) == 2
    assert isinstance(obs[0], VantageProbeObservation)
    assert obs[0].region_id == "ap-southeast-sin"
    assert obs[0].target == "104.16.1.1:443"
    assert obs[0].alive is True
    assert obs[0].latency_ms == 12.4
    assert obs[1].alive is False


def test_vantage_connector_rejects_malformed_payload():
    connector = VantageProbeConnector()
    assert connector.parse_report({}) == []
    assert connector.parse_report({"region_id": "us-west"}) == []
