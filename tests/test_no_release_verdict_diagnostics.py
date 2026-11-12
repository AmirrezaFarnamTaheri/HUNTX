"""No-release artifacts must retain sanitized failure context without secrets."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "write_no_release_verdict.py"
WORKFLOW = ROOT / ".github" / "workflows" / "huntx.yml"


def _run(tmp_path, summary):
    source = tmp_path / "summary.json"
    if summary is not None:
        source.write_text(json.dumps(summary), encoding="utf-8")
    destination = tmp_path / "no-release.json"
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--summary", str(source),
            "--output", str(destination),
            "--run-id", "123",
            "--run-attempt", "2",
            "--source-commit", "a" * 40,
            "--runtime-exit-code", "124",
            "--package-source", "restored",
            "--checkpoint-ready", "true",
        ],
        cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(destination.read_text(encoding="utf-8"))


def test_no_release_receipt_preserves_bounded_failure_diagnostics(tmp_path):
    data = _run(tmp_path, {
        "status": "timed_out",
        "release_eligible": False,
        "metrics": {"timed_out_stage": "build", "build_pending": 1},
        "summary": {
            "timed_out_stage": "build", "build_pending": 1,
            "degraded_source_failures": 28,
        },
        "reasons": ["deadline_exhausted_after_recoverable_progress",
                    "DO_NOT_LEAK_ANYTHING_ELSE"],
        "secret": "SHOULD NEVER LEAK",
    })
    assert data["schema_version"] == 1
    assert data["run_id"] == "123"
    assert data["run_attempt"] == "2"
    assert data["source_commit"] == "a" * 40
    assert data["runtime_exit_code"] == 124
    assert data["checkpoint_ready"] is True
    assert data["release_published"] is False
    assert data["package_ready"] is False
    assert data["timed_out_stage"] == "build"
    assert data["run_status"] == "timed_out"
    assert data["build_pending"] == 1
    assert data["degraded_source_failures"] == 28
    assert "SHOULD NEVER LEAK" not in json.dumps(data)
    assert "DO_NOT_LEAK_ANYTHING_ELSE" not in json.dumps(data)
    assert "deadline_exhausted_after_recoverable_progress" in data["reasons"]


def test_no_release_receipt_fails_closed_without_runtime_summary(tmp_path):
    data = _run(tmp_path, None)
    assert data["run_status"] == "unknown"
    assert data["timed_out_stage"] is None
    assert data["release_published"] is False
    assert data["package_ready"] is False


def test_workflow_uses_sanitized_no_release_writer():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    writer = workflow.split("- name: Record explicit no-release verdict", 1)[1].split(
        "- name: Publish explicit no-release verdict", 1
    )[0]
    assert "python scripts/write_no_release_verdict.py" in writer
    assert "--source-commit" in writer
    assert "--runtime-exit-code" in writer
    assert "--checkpoint-ready" in writer
    assert "--summary" in writer
