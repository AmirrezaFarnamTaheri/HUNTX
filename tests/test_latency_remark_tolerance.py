"""Remark metadata must tolerate non-numeric latency without crashing."""

import pytest

from huntx.formats.npvt import format_enriched_remark


def _counter(scheme):
    return {scheme: 1}


@pytest.mark.parametrize("latency", [12, 12.5, 0])
def test_numeric_latency_is_rendered(latency):
    remark = format_enriched_remark(
        "trojan://pw@host:443",
        _counter("trojan"),
        {"country": "DE", "latency_ms": latency},
    )
    assert f"⚡{latency}ms" in remark


@pytest.mark.parametrize("latency", [None, "fast", True, False, [12], {}])
def test_non_numeric_latency_is_skipped_not_crashing(latency):
    remark = format_enriched_remark(
        "trojan://pw@host:443",
        _counter("trojan"),
        {"country": "DE", "latency_ms": latency},
    )
    assert "⚡" not in remark
    assert "DE" in remark


@pytest.mark.parametrize("latency", [-1, float("inf"), float("nan")])
def test_invalid_numeric_latency_is_skipped(latency):
    remark = format_enriched_remark(
        "trojan://pw@host:443",
        _counter("trojan"),
        {"country": "US", "latency_ms": latency},
    )
    assert "⚡" not in remark


def test_missing_metadata_still_tags():
    remark = format_enriched_remark("trojan://pw@host:443", _counter("trojan"), None)
    # No metadata falls back to the plain scheme-index tag. The counter is
    # incremented before use, so a counter starting at 1 yields index 2.
    assert remark == "trojan-2"


def test_metadata_without_latency_key_is_skipped():
    remark = format_enriched_remark(
        "trojan://pw@host:443",
        _counter("trojan"),
        {"country": "FR"},
    )
    assert "⚡" not in remark
    assert "FR" in remark
