"""Client coverage diagnostics must account for every admitted connection."""
from __future__ import annotations

import json
import hashlib

import pytest

from huntx.formats.npvt import canonical_proxy_identity

from huntx.pipeline.format_coverage import build_client_coverage_report


def test_report_reconciles_each_client_and_never_exposes_credentials():
    nodes = (
        "trojan://SUPER_SECRET@5.5.5.5:443?security=tls#Trojan-1\n"
        "vless://11111111-2222-3333-4444-555555555555@5.5.5.6:80"
        "?security=none#Vless-2"
    )
    from huntx.formats.common.singbox import build_singbox_config_bytes
    from huntx.formats.common.xray import build_xray_config_bytes
    from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes
    from huntx.formats.common.clash import build_clash_subscription_bytes
    report = json.loads(build_client_coverage_report(
        nodes,
        singbox=build_singbox_config_bytes(nodes),
        xray=build_xray_config_bytes(nodes),
        nekobox=build_nekobox_outbounds_bytes(nodes),
        clash=build_clash_subscription_bytes(nodes),
    ))
    assert report["schema_version"] == 1
    assert report["admitted_count"] == 2
    assert len(report["identities"]) == 2
    assert report["formats"]["singbox"]["represented"] == 2
    assert report["formats"]["nekobox"]["represented"] == 2
    assert report["formats"]["clash"]["represented"] == 2
    assert report["formats"]["xray"]["represented"] == 1
    assert report["formats"]["xray"]["omitted"] == 1
    lines = nodes.strip().splitlines()
    digests = [hashlib.sha256(canonical_proxy_identity(line).encode()).hexdigest()
               for line in lines]
    assert report["identities"][digests[0]]["formats"]["xray"]["status"] == "represented"
    omitted = report["identities"][digests[1]]["formats"]["xray"]
    assert omitted["status"] == "unsupported"
    assert omitted["reason"] == "plaintext_transport_not_supported"
    assert report["formats"]["xray"]["reasons"][omitted["reason"]] == 1
    for digest in digests:
        for fmt in ("singbox", "nekobox", "clash"):
            assert report["identities"][digest]["formats"][fmt]["status"] == "represented"
    for result in report["formats"].values():
        assert result["represented"] + result["omitted"] == 2
    assert "SUPER_SECRET" not in json.dumps(report)
    assert "11111111-2222" not in json.dumps(report)
    assert "5.5.5.5" not in json.dumps(report)


def test_report_rejects_silent_converter_disagreement():
    from huntx.formats.common.singbox import build_singbox_config_bytes
    from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes
    from huntx.formats.common.clash import build_clash_subscription_bytes
    import pytest
    node = "trojan://secret@5.5.5.5:443?security=tls#Only"
    with pytest.raises(ValueError, match="unexplained|unmatched"):
        build_client_coverage_report(
            node, singbox=build_singbox_config_bytes(node),
            xray=b'{"outbounds":[{"protocol":"trojan","tag":"NOT-IN-FEED"}]}',
            nekobox=build_nekobox_outbounds_bytes(node),
            clash=build_clash_subscription_bytes(node),
        )


def test_rejects_duplicate_canonical_identity():
    same = "trojan://secret@5.5.5.5:443?security=tls#One"
    other_remark = "trojan://secret@5.5.5.5:443?security=tls#Two"
    with pytest.raises(ValueError, match="duplicate canonical"):
        build_client_coverage_report(
            same + "\\n" + other_remark,
            singbox=b"", xray=b"", nekobox=b"", clash=b"",
        )


def test_rejects_duplicate_client_visible_names():
    lines = (
        "trojan://first@5.5.5.5:443?security=tls#Same\\n"
        "trojan://second@5.5.5.6:443?security=tls#Same"
    )
    with pytest.raises(ValueError, match="duplicate client-visible names"):
        build_client_coverage_report(
            lines, singbox=b"", xray=b"", nekobox=b"", clash=b"",
        )


def test_deduped_after_conversion_is_accounted_for(monkeypatch):
    from huntx.pipeline import format_coverage as coverage
    from huntx.formats.common.singbox import build_singbox_config_bytes
    from huntx.formats.common.xray import build_xray_config_bytes
    from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes
    from huntx.formats.common.clash import build_clash_subscription_bytes

    first = "trojan://first@5.5.5.5:443?security=tls#First"
    second = "trojan://second@5.5.5.6:443?security=tls#Second"
    feed = first + "\\n" + second
    original = coverage._BUILD_ONE["singbox"]
    example = json.loads(original(first))
    first_node = next(node for node in example["outbounds"] if node.get("tag") == "First")
    # This emulates a client converter collapsing distinct canonical
    # connections to a single normalized outbound, while preserving names.
    def make_colliding_single(line):
        name = "First" if "first@" in line else "Second"
        return json.dumps({"outbounds": [{**first_node, "tag": name}]}).encode()

    monkeypatch.setitem(coverage._BUILD_ONE, "singbox", make_colliding_single)
    single = json.dumps({"outbounds": [first_node]}).encode()
    report = json.loads(build_client_coverage_report(
        feed, singbox=single,
        xray=build_xray_config_bytes(feed),
        nekobox=build_nekobox_outbounds_bytes(feed),
        clash=build_clash_subscription_bytes(feed),
    ))
    second_hash = hashlib.sha256(canonical_proxy_identity(second).encode()).hexdigest()
    record = report["identities"][second_hash]["formats"]["singbox"]
    assert record["status"] == "deduped_after_conversion"
    assert record["reason"] == "duplicate_connection_after_conversion"
    assert report["formats"]["singbox"]["represented"] == 1
    assert report["formats"]["singbox"]["omitted"] == 1
