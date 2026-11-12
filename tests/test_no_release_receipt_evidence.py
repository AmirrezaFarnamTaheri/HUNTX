"""Fail-closed no-release receipts retain sanitized cause and source coordinates."""

import hashlib
import json

from scripts.record_no_release_verdict import create_no_release_verdict


def test_timeout_receipt_preserves_specific_failure_evidence(tmp_path):
    summary = tmp_path / "run-summary.json"
    data = {
        "schema_version": 1,
        "status": "timed_out",
        "disposition": "degraded",
        "reasons": [
            "build_work_pending",
            "deadline_exhausted_after_recoverable_progress",
        ],
        "summary": {
            "timed_out_stage": "build",
            "duration_seconds": 5400.01,
            "build_pending": 1,
            "total_artifacts": 0,
            "optional_ingest_err": 28,
            "http_sources_checked": 136,
            "http_sources_failed": 28,
        },
    }
    summary.write_text(json.dumps(data), encoding="utf-8")
    result = create_no_release_verdict(
        summary,
        run_id="43194977065",
        attempt="1",
        source_commit="a" * 40,
        package_source="restored",
        runtime_exit_code="124",
    )

    assert result["schema_version"] == 1
    assert result["release_published"] is False
    assert result["package_ready"] is False
    assert result["source_commit"] == "a" * 40
    assert result["run_id"] == "43194977065"
    assert result["run_attempt"] == "1"
    assert result["package_source"] == "restored"
    assert result["runtime_exit_code"] == 124
    assert result["run_status"] == "timed_out"
    assert result["timed_out_stage"] == "build"
    assert result["build_pending"] == 1
    assert result["source_failures"] == 28
    assert result["summary_sha256"] == hashlib.sha256(summary.read_bytes()).hexdigest()
    assert result["reasons"] == [
        "build_work_pending",
        "deadline_exhausted_after_recoverable_progress",
    ]
    assert "http_source_health" not in result


def test_missing_runtime_summary_cannot_claim_healthy_release(tmp_path):
    result = create_no_release_verdict(
        tmp_path / "missing.json",
        run_id="22",
        attempt="2",
        source_commit="b" * 40,
        package_source="none",
        runtime_exit_code="1",
    )
    assert result["release_published"] is False
    assert result["run_status"] == "unavailable"
    assert result["reasons"] == ["runtime_summary_unavailable"]
    assert result["summary_sha256"] is None


def test_workflow_always_publishes_attributed_no_release_receipt():
    from pathlib import Path

    workflow = Path(".github/workflows/huntx.yml").read_text(encoding="utf-8")
    assert "scripts/record_no_release_verdict.py" in workflow
    assert "--source-commit" in workflow
    assert "--runtime-exit-code" in workflow
    assert "huntx-no-release-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "retention-days: 30" in workflow
