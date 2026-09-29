"""The Xray artifact is a documented subset, and says so.

Earlier this was reported as "Xray silently drops 413 of 1464 nodes - it just
looks a quarter short". That was a misreading: every omission is a deliberate
fail-safe that refuses to emit a config current Xray rejects, or one that would
misrepresent a node's security. The real defect was that nothing reported it, so
an outbound count below the feed read as data loss.

These tests pin both halves: the omission is intentional, and it is attributed.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huntx.formats.common.xray import (  # noqa: E402
    build_xray_config_bytes,
    omission_reason,
    proxy_outbounds_from_uris,
    xray_fidelity_report,
)
from huntx.formats.common.singbox import parse_proxy_uri  # noqa: E402

_REALITY_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
PUBLIC_VLESS = "vless://11111111-2222-3333-4444-555555555555@198.51.100.1:443"


def test_a_fully_representable_feed_reports_no_omission() -> None:
    feed = (
        f"vless://11111111-2222-3333-4444-555555555555@example.com:443"
        f"?security=reality&pbk={_REALITY_KEY}&sid=ab12&sni=cdn.example.com#A"
        "\n"
        "trojan://secret@example.com:443?sni=example.com#B"
        "\n"
    )
    report = xray_fidelity_report(feed)
    assert report["omitted"] == 0
    assert report["unattributed"] == 0
    assert report["represented"] == report["considered"] == 2


def test_a_representable_feed_logs_nothing(caplog) -> None:
    from huntx.pipeline.build import BuildPipeline

    with caplog.at_level(logging.WARNING, logger="huntx.pipeline.build"):
        BuildPipeline._log_xray_fidelity("npvt", b"trojan://secret@example.com:443?sni=example.com#B\n")
    assert caplog.records == []


def test_an_omitted_feed_is_logged_with_the_count_and_reasons(caplog) -> None:
    from huntx.pipeline.build import BuildPipeline

    with caplog.at_level(logging.WARNING, logger="huntx.pipeline.build"):
        BuildPipeline._log_xray_fidelity("npvt", (PUBLIC_VLESS + "\n").encode())
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "npvt.xray.json" in message
    assert "represents 0 of 1 nodes" in message
    assert "plaintext VLESS" in message


def test_the_report_survives_the_production_log_level(caplog) -> None:
    """huntx.yml pins LOG_LEVEL=INFO, so a WARNING must actually be emitted."""
    from huntx.pipeline.build import BuildPipeline

    with caplog.at_level(logging.INFO, logger="huntx.pipeline.build"):
        BuildPipeline._log_xray_fidelity("npvt", (PUBLIC_VLESS + "\n").encode())
    assert [r for r in caplog.records if r.levelno == logging.WARNING]


def test_an_omission_is_attributed_to_a_named_guard() -> None:
    """Plaintext VLESS to a public address: Xray refuses to load such a node."""
    report = xray_fidelity_report(PUBLIC_VLESS + "\n")
    assert report["considered"] == 1
    assert report["represented"] == 0
    assert report["omitted"] == 1
    assert report["unattributed"] == 0
    reasons = " ".join(report["reasons"])
    assert "plaintext VLESS to a public address" in reasons


def test_allow_insecure_is_reported_as_removed_not_silently_dropped() -> None:
    feed = "vless://11111111-2222-3333-4444-555555555555@198.51.100.1:443?security=tls&allowInsecure=1#A\n"
    report = xray_fidelity_report(feed)
    assert report["omitted"] == 1
    assert "allowInsecure" in " ".join(report["reasons"])


def test_an_unknown_utls_fingerprint_is_reported() -> None:
    feed = (
        f"vless://11111111-2222-3333-4444-555555555555@198.51.100.1:443"
        f"?security=reality&pbk={_REALITY_KEY}&sid=ab12&sni=c.example.com&fp=unsafe#A\n"
    )
    report = xray_fidelity_report(feed)
    assert report["omitted"] == 1
    assert "uTLS fingerprint" in " ".join(report["reasons"])


def test_every_omission_on_the_shipped_feed_is_attributed() -> None:
    """The whole point: a lower outbound count must never be unexplained."""
    feed_path = ROOT / "outputs" / "all_sources.npvt"
    if not feed_path.exists():
        pytest.skip("no local production snapshot to analyse")
    report = xray_fidelity_report(feed_path.read_text(encoding="utf-8"))
    assert report["unattributed"] == 0, report["reasons"]
    assert report["omitted"] == sum(report["reasons"].values())
    assert report["considered"] == report["represented"] + report["omitted"]


def test_the_reported_counts_match_the_artifact() -> None:
    feed_path = ROOT / "outputs" / "all_sources.npvt"
    if not feed_path.exists():
        pytest.skip("no local production snapshot to analyse")
    text = feed_path.read_text(encoding="utf-8")
    report = xray_fidelity_report(text)
    config = json.loads(build_xray_config_bytes(text))
    proxies = [o for o in config["outbounds"] if o["protocol"] not in ("freedom",)]
    assert len(proxies) == report["represented"]


def test_omission_reason_names_a_guard_for_every_rejection() -> None:
    node = parse_proxy_uri(PUBLIC_VLESS)
    assert node is not None
    reason = omission_reason(PUBLIC_VLESS, node)
    assert reason
    assert reason != "omitted without a stated reason"


def test_an_unparseable_link_is_named_as_such() -> None:
    assert omission_reason("not-a-link", None) == "unparseable share link"


def test_proxy_outbounds_from_uris_collects_omissions_when_asked() -> None:
    import collections

    feed = [PUBLIC_VLESS, "trojan://secret@example.com:443?sni=example.com#B"]
    collected: collections.Counter = collections.Counter()
    outbounds = proxy_outbounds_from_uris(feed, collected)
    assert len(outbounds) == 1
    assert sum(collected.values()) == 1
