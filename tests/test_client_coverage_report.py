"""Client coverage diagnostics must account for every admitted connection."""
from __future__ import annotations

import json

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
