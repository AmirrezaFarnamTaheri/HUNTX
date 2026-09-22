"""Missing measurements must not become invented health or location labels."""
import pytest

from huntx.formats.npvt import format_enriched_remark

URI = "vless://00000000-0000-4000-8000-000000000001@example.invalid:443"


@pytest.mark.parametrize("latency", [None, "42", True, -1, float("nan"), float("inf")])
def test_invalid_latency_is_not_displayed(latency):
    remark = format_enriched_remark(URI, {}, {"latency_ms": latency})
    assert "⚡" not in remark


@pytest.mark.parametrize("latency", [0, 42, 42.5])
def test_nonnegative_finite_latency_is_displayed(latency):
    remark = format_enriched_remark(URI, {}, {"latency_ms": latency})
    assert f"⚡{latency}ms" in remark


@pytest.mark.parametrize("country", [None, "", "ZZ", "USA", 42, "éé"])
def test_unknown_country_is_not_invented(country):
    remark = format_enriched_remark(URI, {}, {"country": country})
    assert remark.startswith("🌐 ZZ | VLESS")


def test_missing_country_does_not_default_to_germany():
    assert format_enriched_remark(URI, {}, {"latency_ms": 42}).startswith("🌐 ZZ")


@pytest.mark.parametrize("grade", [None, "", "-", "  ", 42, True])
def test_missing_grade_is_not_displayed(grade):
    remark = format_enriched_remark(URI, {}, {"health_grade": grade})
    assert "⭐" not in remark


def test_metadata_normalization_and_sequence():
    counter = {}
    metadata = {"country": " de ", "operator": "CF", "health_grade": "A+", "latency_ms": 42}
    first = format_enriched_remark(URI, counter, metadata)
    second = format_enriched_remark(URI.replace("vless://", "Vless://"), counter, metadata)
    assert first == "🇩🇪 DE-CF | VLESS | ⚡42ms | ⭐A+ | #001"
    assert second.endswith("#002")
    assert metadata["country"] == " de "


@pytest.mark.parametrize("transport,security,expected", [
    ("grpc", "reality", "VLESS-GRPC-REALITY"),
    ("ws", "", "VLESS-WS"),
    ("tcp", "tls", "VLESS-TCP-TLS"),
    ("", "", "VLESS"),
])
def test_transport_and_security_are_shown_in_the_protocol_tag(transport, security, expected):
    """Transport and security belong in the remark so nodes differ at a glance."""
    remark = format_enriched_remark(URI, {}, {"country": "DE", "transport": transport, "security": security})
    assert f"DE | {expected} |" in remark


@pytest.mark.parametrize("junk", ["none", "auto", "unknown", "NONE"])
def test_placeholder_transport_values_are_not_displayed(junk):
    remark = format_enriched_remark(URI, {}, {"country": "DE", "transport": junk})
    assert "DE | VLESS-" not in remark
    assert "DE | VLESS |" in remark
