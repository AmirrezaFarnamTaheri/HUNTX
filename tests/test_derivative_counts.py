"""Derived captions must reflect emitted nodes, not source-record totals."""
import base64
import json

import pytest

from huntx.pipeline.build import BuildPipeline


@pytest.mark.parametrize(
    ("fmt", "payload", "expected"),
    [
        ("npvt.decoded.json", json.dumps({"entries": [{"protocol": "vless"}]}).encode(), 1),
        ("npvt.singbox.json", json.dumps({"outbounds": [{"type": "vless"}]}).encode(), 1),
        ("npvt.xray.json", json.dumps({"outbounds": [{"protocol": "vmess"}]}).encode(), 1),
        ("npvt.nekobox.json", json.dumps([{"type": "trojan", "tag": "node"}]).encode(), 1),
        ("npvt.clash.yaml", b'proxies:\n  - {"name":"a","type":"trojan"}\n', 1),
        ("npvt.b64sub", base64.b64encode(b"vless://a\ntrojan://b\n"), 2),
        (
            "npvt.singbox.profile.json",
            json.dumps({"outbounds": [
                {"type": "selector"}, {"type": "direct"}, {"type": "vless"},
            ]}).encode(),
            1,
        ),
        (
            "npvt.xray.profile.json",
            json.dumps({"outbounds": [
                {"protocol": "freedom"}, {"protocol": "trojan"},
            ]}).encode(),
            1,
        ),
    ],
)
def test_derived_node_count_excludes_full_profile_policy(fmt, payload, expected):
    assert BuildPipeline._derived_node_count(fmt, payload) == expected


def test_nekobox_node_count_rejects_full_configuration_objects():
    with pytest.raises(ValueError, match="NekoBox node feed"):
        BuildPipeline._derived_node_count(
            "npvt.nekobox.json",
            json.dumps({"outbounds": [{"type": "trojan", "tag": "node"}]}).encode(),
        )
