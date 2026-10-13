"""Corpus-wide network diagnostic sampling and credential-safe aggregation."""

import json
from unittest.mock import AsyncMock

import pytest

from scripts.report_network_diagnostics import (
    build_network_candidates,
    inspect_corpus,
)


UUID1 = "11111111-2222-3333-4444-555555555555"
UUID2 = "22222222-2222-4333-8333-666666666666"


def observations():
    return [
        ("s1", json.dumps({"line": f"vless://{UUID1}@1.1.1.1:443?security=tls#SECRET"})),
        ("s2", json.dumps({"line": f"vless://{UUID2}@1.1.1.1:443?security=tls#FR"})),
        ("s3", json.dumps({"line": "trojan://password@proxy.example.com:443?security=tls"})),
        ("s4", json.dumps({"line": "hysteria2://secret@8.8.8.8:443"})),
        ("s5", json.dumps({"line": "vless://secret@10.0.0.1:443"})),
        ("s6", json.dumps({"line": "not-a-proxy"})),
    ]


def test_corpus_candidates_are_deduped_and_never_emit_passwords():
    candidates, counts = build_network_candidates(observations())
    assert len(candidates) == 3
    assert counts["records_seen"] == 6
    assert counts["duplicate_network_endpoints"] == 1
    assert counts["non_public_endpoints"] == 1
    assert counts["invalid_records"] == 1
    assert any(item["protocol"] == "hysteria2" for item in candidates)
    assert all(item["host_kind"] != "non_public_ip_literal" for item in candidates)


@pytest.mark.asyncio
async def test_layered_report_samples_endpoints_and_rolls_up_independent_statuses():
    inspector = AsyncMock(side_effect=[
        {
            "endpoint_id": "a" * 24, "protocol": "vless",
            "dns": {"status": "resolved_public"},
            "tcp": {"status": "connected"},
            "tls": {"status": "verified_handshake"},
            "transport_protocol": {"status": "unverified"},
            "proxy_protocol": {"status": "unverified"},
            "disposition": "recoverable", "terminal": False,
        },
        {
            "endpoint_id": "b" * 24, "protocol": "trojan",
            "dns": {"status": "timeout"},
            "tcp": {"status": "not_attempted"},
            "tls": {"status": "not_attempted"},
            "transport_protocol": {"status": "unverified"},
            "proxy_protocol": {"status": "unverified"},
            "disposition": "recoverable", "terminal": False,
        },
    ])
    target_list = [
        {"endpoint_id": "a" * 24, "protocol": "vless"},
        {"endpoint_id": "b" * 24, "protocol": "trojan"},
    ]
    payload = await inspect_corpus(target_list, inspector=inspector, limit=2, seed="run1")
    assert payload["status"] == "complete"
    assert payload["counts"]["tested"] == 2
    assert payload["counts"]["terminal"] == 0
    assert payload["layers"]["dns"]["resolved_public"] == 1
    assert payload["layers"]["dns"]["timeout"] == 1
    assert payload["layers"]["proxy_protocol"]["unverified"] == 2
    assert "never_equivalent_to_authenticated_proxy_health" in payload["evidence_limits"]
    serialized = json.dumps(payload)
    assert "password" not in serialized
    assert "proxy.example.com" not in serialized


@pytest.mark.asyncio
async def test_disable_network_retains_explicit_unknown_instead_of_falsely_healthy():
    inspector = AsyncMock()
    payload = await inspect_corpus(
        [{"endpoint_id": "a" * 24, "protocol": "vless"}],
        inspector=inspector, enabled=False, limit=1, seed="disabled",
    )
    assert payload["status"] == "disabled"
    assert payload["counts"]["tested"] == 0
    inspector.assert_not_awaited()


def test_nonpublic_endpoints_cannot_enter_the_network_sampling_list():
    targets, counts = build_network_candidates([
        ("a", json.dumps({"line": "vless://key@169.254.169.254:80"})),
        ("a", json.dumps({"line": "vless://key@198.18.0.1:443"})),
        ("a", json.dumps({"line": "vless://key@127.0.0.1:443"})),
    ])
    assert targets == []
    assert counts["non_public_endpoints"] == 3
