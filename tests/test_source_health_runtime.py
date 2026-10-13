"""Regressions for source attribution and production Go worker availability."""

from pathlib import Path

import pytest

from huntx.core.orchestrator import Orchestrator
from huntx.core.run_health import evaluate_run_health


def test_missing_go_feed_worker_is_a_distinct_infrastructure_failure(tmp_path, monkeypatch):
    from huntx.connectors.http_subscription.connector import (
        GoFeedWorkerUnavailable,
        _engine_path,
    )

    monkeypatch.setenv("HUNTX_ENGINE_BIN", str(tmp_path / "not-installed"))
    with pytest.raises(GoFeedWorkerUnavailable, match="does not exist"):
        _engine_path()


def test_infrastructure_failure_does_not_poison_feed_reliability():
    class Repo:
        def __init__(self):
            self.state = {
                "feed_sha256": "a" * 64,
                "previous_successes": 3,
                "total_failures": 1,
                "consecutive_failures": 1,
                "retrieval_history": [{"at": 1800000000, "ok": True, "nodes": 2}],
            }

        def get_source_state(self, source_id):
            assert source_id == "feed-id"
            return dict(self.state)

        def update_source_state(self, source_id, state, source_type="telegram"):
            assert source_id == "feed-id"
            assert source_type == "http_subscription"
            self.state = dict(state)

    app = Orchestrator.__new__(Orchestrator)
    app.repo = Repo()
    app._http_source_reports = {}
    app._record_http_source_failure(
        "feed-id", "GoFeedWorkerUnavailable", infrastructure=True
    )
    state = app.repo.state
    assert state["total_failures"] == 1
    assert state["consecutive_failures"] == 1
    assert len(state["retrieval_history"]) == 1
    assert state["previous_successes"] == 3
    assert state["last_infrastructure_error_type"] == "GoFeedWorkerUnavailable"
    report = app._http_source_reports["feed-id"]
    assert report["status"] == "infrastructure_error"
    assert report["availability"]["failures"] == 1


def test_run_health_reports_worker_outages_separately_from_feed_errors():
    health = evaluate_run_health({
        "status": "completed", "total_artifacts": 1, "ingest_ok": 10,
        "optional_ingest_err": 2, "http_sources_checked": 2,
        "http_sources_failed": 0, "http_sources_infrastructure_errors": 2,
    })
    assert health.disposition == "degraded"
    assert "http_feed_worker_unavailable" in health.reasons
    assert health.metrics["http_sources_failed"] == 0
    assert health.metrics["http_sources_infrastructure_errors"] == 2


def test_production_builds_worker_in_actual_ingestion_job_and_tracks_sources():
    workflow = Path(".github/workflows/huntx.yml").read_text(encoding="utf-8")
    run_job = workflow.split("  run:\n    name: ingest-build-package", 1)[1].split("\n  persist:", 1)[0]
    build = run_job.split("      - name: Build release tools", 1)[1].split(
        "      - name: Set up Python", 1
    )[0]
    assert "go build -o .bin/huntx-engine ./cmd/huntx-engine" in build
    assert "test -x .bin/huntx-engine" in build
    assert run_job.index("test -x .bin/huntx-engine") < run_job.index(
        "Run HuntX with controlled watchdog"
    )
    diagnostics = run_job.split("      - name: Publish structured runtime diagnostics", 1)[1]
    assert "python scripts/report_source_health.py" in diagnostics
    assert "--output persist/data/logs/source-health.json" in diagnostics
    assert "Upload logs and structured diagnostics" in diagnostics
