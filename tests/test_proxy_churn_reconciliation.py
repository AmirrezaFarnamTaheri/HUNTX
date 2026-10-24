"""Snapshot churn is a countable identity delta, not a dead-proxy claim."""
import hashlib
import json

from huntx.formats.npvt import canonical_proxy_identity
from scripts.assemble_generated_snapshot import build_proxy_churn_report


def test_proxy_churn_attributes_current_gate_and_variant_differences(tmp_path):
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    for root in (previous, current):
        (root / "outputs").mkdir(parents=True)
    gone = "trojan://alpha@5.5.5.5:443?security=tls#Old"
    shared = "trojan://beta@5.5.5.6:443?security=tls#Shared"
    fresh = "trojan://gamma@5.5.5.7:443?security=tls#New"
    previous.joinpath("outputs/all_sources.txt").write_text(
        gone + "\n" + shared + "\n", encoding="utf-8"
    )
    current.joinpath("outputs/all_sources.txt").write_text(
        shared + "\n" + fresh + "\n", encoding="utf-8"
    )
    current.joinpath("outputs/all_sources_sub.txt").write_text(
        gone + "\n" + shared + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(canonical_proxy_identity(gone).encode()).hexdigest()
    current.joinpath("outputs/all_sources_gate.json").write_text(
        json.dumps({
            "schema_version": 1, "identities": {digest: "https_path_failed"},
            "candidates": 1, "admitted": 0, "rejected": 1,
            "reasons": {"https_path_failed": 1},
        }), encoding="utf-8",
    )
    report = build_proxy_churn_report(
        current / "outputs", previous / "outputs"
    )
    assert report["schema_version"] == 1
    assert report["current_count"] == 2
    assert report["previous_count"] == 2
    assert report["retained_count"] == 1
    assert report["appeared_count"] == 1
    assert report["disappeared_count"] == 1
    assert report["disappeared"][digest]["current_gate_status"] == "https_path_failed"
    assert report["variants"]["base_only_count"] == 1
    assert report["variants"]["sub_only_count"] == 1
    assert "alpha@" not in json.dumps(report)
    assert "gamma@" not in json.dumps(report)
