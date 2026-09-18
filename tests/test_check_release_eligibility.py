"""Fail-closed publication gate; tests do not ingest or publish anything."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path("scripts/check_release_eligibility.py")


def module():
    spec = importlib.util.spec_from_file_location("check_release_eligibility", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.mark.parametrize("value", [False, None, 0, 1, "true", {}, []])
def test_only_literal_true_allows_publication(tmp_path, value):
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"summary": {"release_eligible": value}}))
    with pytest.raises(ValueError):
        module().check_health(health, 0)


@pytest.mark.parametrize("exit_code", [1, 124, 137, 143])
def test_runtime_failure_overrides_eligible_health(tmp_path, exit_code):
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"summary": {"release_eligible": True}}))
    with pytest.raises(ValueError):
        module().check_health(health, exit_code)


@pytest.mark.parametrize("payload", ["garbage", "[]", "null", "{}", '{"release_eligible":true}', '{"summary":[]}'])
def test_invalid_or_missing_health_fails_closed(tmp_path, payload):
    health = tmp_path / "health.json"
    health.write_text(payload)
    with pytest.raises(ValueError):
        module().check_health(health, 0)
    with pytest.raises(ValueError):
        module().check_health(tmp_path / "missing.json", 0)


def test_success_uses_nested_summary_and_retains_cutoff(tmp_path):
    summary = {"release_eligible": True, "min_ingested_at": "2026-09-14 12:00:00"}
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"summary": summary}))
    assert module().check_health(health, 0) == summary


def test_production_gate_precedes_package_and_summary_cannot_be_restored():
    workflow = Path(".github/workflows/huntx.yml").read_text()
    assert workflow.index('mv "$HUNTX_RUN_SUMMARY_PATH"') < workflow.index("timeout --signal=TERM")
    package = workflow[workflow.index("- name: Verify and package recoverable output"):]
    assert package.index("scripts/check_release_eligibility.py") < package.index("if try_package docs-candidate")
    assert "for directory in outputs outputs_dev dist" in workflow
    assert "No fresh release will be published" in package


def test_publisher_checks_release_receipt_before_regeneration():
    workflow = Path(".github/workflows/publish-generated-outputs.yml").read_text()
    assert workflow.index("Download structured runtime diagnostics") < workflow.index("Build verified dashboard")
    assert workflow.index("scripts/check_release_eligibility.py") < workflow.index("Build verified dashboard")
    assert "SOURCE_CREATED_AT: ${{ steps.release.outputs.generated_at }}" in workflow
    assert '--empty-release' in workflow


def make_dist(tmp_path, *, empty=False):
    from huntx.store.release_manifest import build_release_manifest, write_manifest_atomic

    dist = tmp_path / "dist"
    dist.mkdir()
    if empty:
        artifact = dist / "empty-release.json"
        artifact.write_text(json.dumps({
            "schema_version": 1, "status": "success", "record_count": 0,
            "reason": "no_eligible_records", "generated_at": "2026-09-17T12:00:00Z",
        }))
    else:
        artifact = dist / "fixture.json"
        artifact.write_text('{"entries":[]}')
    write_manifest_atomic(dist / "manifest.json", build_release_manifest(dist, [artifact]))
    return dist


@pytest.mark.parametrize("empty", [False, True])
def test_receipt_roundtrip_preserves_timestamp_and_manifest(tmp_path, empty):
    gate = module()
    dist = make_dist(tmp_path, empty=empty)
    receipt = gate.build_receipt(dist, {"min_ingested_at": "2026-09-14 12:00:00"}, "123", "2")
    original = dict(receipt)
    if empty:
        assert receipt["generated_at"] == "2026-09-17T12:00:00+00:00"
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    assert gate.verify_receipt(path, dist, "123", "2") == original
    assert receipt["empty_release"] is empty


@pytest.mark.parametrize("field,value", [
    ("source_run_id", "999"), ("source_run_attempt", "1"), ("release_eligible", "true"),
    ("runtime_exit_code", False), ("runtime_exit_code", 124), ("package_source", "restored"),
    ("manifest_sha256", "0" * 64), ("empty_release", "false"), ("generated_at", "yesterday"),
    ("generated_at", "2026-09-17T12:00:00"),
])
def test_invalid_receipts_fail_closed(tmp_path, field, value):
    gate = module()
    dist = make_dist(tmp_path)
    receipt = gate.build_receipt(dist, {}, "123", "2")
    receipt[field] = value
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        gate.verify_receipt(path, dist, "123", "2")


def test_changed_artifact_cannot_reuse_receipt(tmp_path):
    gate = module()
    dist = make_dist(tmp_path)
    receipt = gate.build_receipt(dist, {}, "123", "2")
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    (dist / "fixture.json").write_text('{"entries":["modified"]}')
    with pytest.raises(ValueError):
        gate.verify_receipt(path, dist, "123", "2")


def test_cli_gate_receipt_and_empty_without_decoded_artifact(tmp_path):
    import os
    import subprocess
    import sys

    dist = make_dist(tmp_path, empty=True)
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"summary": {"release_eligible": True}}))
    receipt = tmp_path / "receipt.json"
    output = tmp_path / "github-output"
    env = dict(os.environ, GITHUB_OUTPUT=str(output), PYTHONPATH=str(Path("src").resolve()))
    common = [sys.executable, str(SCRIPT)]
    result = subprocess.run(common + [
        "--health", str(health), "--runtime-exit-code", "0", "--dist", str(dist),
        "--run-id", "123", "--run-attempt", "2", "--receipt", str(receipt),
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    original = receipt.read_bytes()
    result = subprocess.run(common + [
        "--verify-receipt", str(receipt), "--dist", str(dist), "--run-id", "123", "--run-attempt", "2",
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert receipt.read_bytes() == original
    assert output.read_text().count("generated_at=2026-09-17T12:00:00+00:00") == 2
    result = subprocess.run(common + ["--empty-release", "--dist", str(dist)], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    result = subprocess.run(common + [
        "--health", str(health), "--runtime-exit-code", "124",
    ], capture_output=True, text=True)
    assert result.returncode == 1
