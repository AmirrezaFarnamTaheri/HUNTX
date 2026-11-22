"""Historical subscriptions can deploy without faking a fresh proxy release."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.assemble_generated_snapshot import (
    write_compressed_dev_manifest,
    write_snapshot_digest,
    verify_snapshot_digest,
)
from scripts.publish_historical_subscriptions import prepare_historical_pages


ARCHIVED_AT = "2026-11-11T10:45:05.848392+00:00"


def _previous_publication(tmp_path: Path) -> tuple[Path, Path]:
    previous = tmp_path / "previous"
    previous.mkdir()
    manifest = {
        "trojan://password@archive.example:443": 1731200000,
        "socks5://user:password@socks.example:1080": 1731200300,
    }
    dev = previous / "outputs_dev"
    dev.mkdir()
    write_compressed_dev_manifest(dev, manifest)
    receipt = {
        "schema_version": 3,
        "source_run_id": "42995132362",
        "source_run_attempt": 1,
        "source_commit": "a" * 40,
        "source_created_at": ARCHIVED_AT,
        "outputs_scope": "source_run",
        "outputs_dev_scope": "all_time_cumulative",
    }
    (previous / "manifests").mkdir()
    (previous / "manifests" / "publication.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    docs = previous / "docs"
    (docs / "artifacts" / "release").mkdir(parents=True)
    (docs / "artifacts" / "release" / "manifest.json").write_text(
        '{"artifact_count":0,"artifacts":[]}', encoding="utf-8"
    )
    (docs / "catalog.json").write_text(
        '{"files":[],"total_files":0,"total_size":0}', encoding="utf-8"
    )
    (docs / "index.html").write_text(
        '<html><nav><a href="network-doctor.html">Fix connection ↗</a></nav></html>',
        encoding="utf-8",
    )
    (docs / "assets" / "js").mkdir(parents=True)
    (docs / "assets" / "js" / "data.js").write_text("const VERIFIED_RELEASE = true;\n")
    write_snapshot_digest(previous)

    # New subscription shell is only taken from the reviewed current main.
    source = tmp_path / "main" / "docs"
    (source / "assets" / "js").mkdir(parents=True)
    (source / "assets" / "css").mkdir(parents=True)
    (source / "subscriptions.html").write_text("<title>Subscription library</title>")
    (source / "assets" / "js" / "subscription-library.js").write_text("export {};")
    (source / "assets" / "css" / "subscription-library.css").write_text(":root {}")
    return previous, source


def test_historical_feeds_publish_from_unchanged_verified_cumulative_history(tmp_path):
    previous, source = _previous_publication(tmp_path)
    old_receipt = (previous / "manifests" / "publication.json").read_bytes()
    old_release = (previous / "docs" / "artifacts" / "release" / "manifest.json").read_bytes()
    target = tmp_path / "built"

    index = prepare_historical_pages(previous, source, target, "b" * 40)
    verify_snapshot_digest(target)

    assert index["scope"] == "all_time_cumulative"
    assert index["generated_at"] == ARCHIVED_AT
    assert index["health_status"] == "historical_unverified"
    assert index["limit_per_protocol"] == 100
    assert index["protocols"]["trojan"]["count"] == 1
    assert index["protocols"]["socks"]["count"] == 1
    assert index["protocols"]["slipnet"]["count"] == 0
    assert index["aggregate"]["count"] == 2
    site = target / "docs"
    assert (site / "subscriptions.html").read_bytes() == (source / "subscriptions.html").read_bytes()
    assert "subscriptions.html" in (site / "index.html").read_text()
    assert (site / "subscriptions" / "latest" / "all.txt").read_bytes() == (
        site / "artifacts" / "dev" / "latest" / "all.txt"
    ).read_bytes()
    assert (site / "artifacts" / "dev" / "proxies.json").is_file()
    assert (site / "assets" / "js" / "data.js").read_text() == "const VERIFIED_RELEASE = true;\n"
    assert (target / "manifests" / "publication.json").read_bytes() == old_receipt
    assert (site / "artifacts" / "release" / "manifest.json").read_bytes() == old_release
    receipt = json.loads((target / "manifests" / "historical-subscriptions.json").read_text())
    assert receipt["publication_type"] == "historical_only"
    assert receipt["source_run_id"] == "42995132362"
    assert receipt["source_commit"] == "a" * 40
    assert receipt["control_commit"] == "b" * 40
    assert receipt["verified_release_preserved"] is True


def test_historical_publication_fails_closed_on_changed_prior_snapshot(tmp_path):
    previous, source = _previous_publication(tmp_path)
    (previous / "outputs_dev" / "_manifest.json.gz.part0001").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest mismatch"):
        prepare_historical_pages(previous, source, tmp_path / "built", "b" * 40)


def test_historical_publication_fails_closed_without_history(tmp_path):
    previous, source = _previous_publication(tmp_path)
    (previous / "outputs_dev" / "_manifest.json.gz.index.json").unlink()
    write_snapshot_digest(previous)
    with pytest.raises(ValueError, match="cumulative manifest"):
        prepare_historical_pages(previous, source, tmp_path / "built", "b" * 40)


def test_historical_workflow_can_deploy_without_producer_release():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/publish-historical-subscriptions.yml"
    ).read_text(encoding="utf-8")
    assert "push:" in workflow and "publish-historical-subscriptions.yml" in workflow
    assert "publish-generated-outputs" in workflow  # Share publisher concurrency lock.
    assert "upload-pages-artifact@" in workflow
    assert "deploy-pages@" in workflow
    assert "verify_deployed_pages.py" in workflow
    assert workflow.index("verify_deployed_pages.py") < workflow.index("git push")
    assert "release_eligible=false" not in workflow
