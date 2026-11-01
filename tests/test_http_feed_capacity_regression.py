"""Large approved HTTPS subscriptions must not be rejected by obsolete caps.

These are source-import limits, not authentication or release-membership gates.
Oversized or unsafe inputs must still fail closed rather than being truncated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from huntx.connectors.http_subscription import parser


UUID = "f58a62e3-27a0-4297-906c-2d01b12eff32"


def _uri(port: int) -> str:
    return (
        f"vless://{UUID}@1.1.1.1:{port}"
        f"?security=tls&sni=example.com#node-{port}"
    )


def test_more_than_9000_unique_nodes_survive_source_normalization():
    links = [_uri(port) for port in range(10000, 19001)]
    normalized, report = parser.normalize_feed(("\n".join(links) + "\n").encode())
    assert report["nodes"] == len(links) == 9001
    assert normalized.decode().splitlines() == links


def test_feed_larger_than_5_mib_is_accepted_when_it_contains_a_valid_node():
    payload = (_uri(443) + "\n").encode() + b" " * (5 * 1024 * 1024)
    normalized, report = parser.normalize_feed(payload)
    assert report["nodes"] == 1
    assert normalized.decode().strip() == _uri(443)


def test_valid_mihomo_yaml_larger_than_2_mib_is_parsed():
    node = (
        "proxies:\n"
        "  - type: vless\n"
        "    name: sampled\n"
        "    server: 1.1.1.1\n"
        "    port: 443\n"
        f"    uuid: {UUID}\n"
        "    tls: true\n"
    ).encode()
    payload = node + b"#" + b"c" * (2 * 1024 * 1024) + b"\n"
    normalized, report = parser.normalize_feed(payload)
    assert report["kind"] == "mihomo"
    assert report["nodes"] == 1
    assert normalized.decode().startswith("vless://")


def test_larger_source_caps_remain_finite_and_match_go_retrieval():
    assert 16 * 1024 * 1024 <= parser.MAX_FEED_BYTES <= 32 * 1024 * 1024
    assert 30_000 <= parser.MAX_FEED_NODES <= 60_000
    assert 8 * 1024 * 1024 <= parser.MAX_MIHOMO_YAML_BYTES <= parser.MAX_FEED_BYTES

    root = Path(__file__).resolve().parents[1]
    go_source = (root / "cmd/huntx-engine/subfeed/fetch.go").read_text()
    match = re.search(r"const MaxBodyBytes = (\d+) \* 1024 \* 1024", go_source)
    assert match is not None
    assert int(match.group(1)) * 1024 * 1024 == parser.MAX_FEED_BYTES


def test_node_ceiling_still_rejects_whole_input_without_truncating():
    payload = json.dumps([_uri(443)] * (parser.MAX_FEED_NODES + 1)).encode()
    with pytest.raises(ValueError, match="node limit"):
        parser.normalize_feed(payload)


def test_base64_expansion_cannot_bypass_feed_byte_cap():
    import base64

    # Encoded body is within the fetch limit, but decoded content exceeds it.
    expanded = b"x" * (parser.MAX_FEED_BYTES + 1)
    encoded = base64.b64encode(expanded)
    if len(encoded) <= parser.MAX_FEED_BYTES:
        with pytest.raises(ValueError, match="decoded feed exceeds bounded size"):
            parser.normalize_feed(encoded)
    else:
        # The raw transfer cap rejects this even before decoding.
        with pytest.raises(ValueError, match="oversized"):
            parser.normalize_feed(encoded)
