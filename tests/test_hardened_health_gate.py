import json
import logging

from huntx.cli.hardened_main import _all_publish_failures_are_fatal
from huntx.core.run_health import emit_run_health, evaluate_run_health


def test_all_publish_failures_are_degraded_not_fatal():
    summary = {
        "status": "partial",
        "total_artifacts": 2,
        "publish_attempts": 2,
        "publish_failures": 2,
        "ingest_ok": 3,
    }

    assert not _all_publish_failures_are_fatal(summary, no_publish=False)
    health = evaluate_run_health(summary)
    assert health.disposition == "degraded"
    assert "all_publish_attempts_failed" in health.reasons


def test_deadline_with_recoverable_progress_is_degraded_success():
    health = evaluate_run_health(
        {
            "status": "timed_out",
            "timed_out_stage": "publishing",
            "total_artifacts": 4,
            "ingest_ok": 10,
            "publish_pending": 1,
        }
    )

    assert health.disposition == "degraded"
    assert health.recoverable_progress is True
    assert "deadline_exhausted_after_recoverable_progress" in health.reasons


def test_deadline_without_any_progress_remains_fatal():
    health = evaluate_run_health(
        {
            "status": "timed_out",
            "timed_out_stage": "initialization",
            "total_artifacts": 0,
            "ingest_ok": 0,
            "ingest_err": 0,
        }
    )

    assert health.disposition == "fatal"
    assert "deadline_exhausted_without_recoverable_progress" in health.reasons


def test_all_source_failures_are_isolated_as_degraded():
    health = evaluate_run_health(
        {
            "status": "failed",
            "total_artifacts": 0,
            "ingest_ok": 0,
            "ingest_err": 8,
        }
    )

    assert health.disposition == "degraded"
    assert "source_failures" in health.reasons


def test_explicit_configuration_failure_remains_fatal():
    health = evaluate_run_health(
        {
            "status": "failed",
            "reason": "no_approved_sources",
            "total_artifacts": 0,
        }
    )

    assert health.disposition == "fatal"
    assert "no_approved_sources" in health.reasons


def test_completed_noop_is_degraded_not_failed():
    health = evaluate_run_health(
        {
            "status": "completed",
            "total_artifacts": 0,
            "ingest_ok": 4,
            "ingest_err": 0,
        }
    )

    assert health.disposition == "degraded"
    assert "no_new_artifacts" in health.reasons


def test_run_health_report_is_atomic_and_machine_readable(tmp_path):
    report_path = tmp_path / "logs" / "run-summary.json"
    summary = {
        "status": "partial",
        "total_artifacts": 3,
        "ingest_ok": 7,
        "ingest_err": 1,
    }
    health = evaluate_run_health(summary)

    payload = emit_run_health(
        summary,
        health,
        logger=logging.getLogger("test-run-health"),
        path=report_path,
    )

    assert report_path.exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted == payload
    assert persisted["schema_version"] == 1
    assert persisted["disposition"] == "degraded"
    assert persisted["summary"]["total_artifacts"] == 3
