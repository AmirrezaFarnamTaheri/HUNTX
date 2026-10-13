"""Regressions for credential-free, campaign-scoped source health reports."""

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.report_source_health import build_snapshot, load_queue_evidence


def sample_config():
    return [
        {"id": "http_ok", "type": "http_subscription",
         "http_subscription": {"enabled": True, "url": "https://secret.invalid/?token=HIDDEN"}},
        {"id": "http_system", "type": "http_subscription", "http_subscription": {"enabled": True}},
        {"id": "http_failed", "type": "http_subscription", "http_subscription": {"enabled": True}},
        {"id": "http_off", "type": "http_subscription", "http_subscription": {"enabled": False}},
        {"id": "telegram_good", "type": "telegram_user", "telegram_user": {"session": "PRIVATE"}},
        {"id": "telegram_retry", "type": "telegram_user"},
        {"id": "telegram_missing", "type": "telegram_user"},
        {"id": "retired", "type": "telegram_user", "trust_state": "retired"},
    ]


def report():
    return {
        "summary": {
            "lifo_campaign_id": 4,
            "http_source_health": {
                "http_ok": {
                    "status": "parsed", "checked_at": 1800000000,
                    "nodes": 35, "validation": "syntax_only",
                    "availability": {
                        "successes": 4, "failures": 1,
                        "freshness": "recent", "rolling_success_rate": 0.8,
                    },
                },
                "http_system": {
                    "status": "infrastructure_error", "error_type": "GoFeedWorkerUnavailable",
                    "availability": {"successes": 2, "failures": 0},
                },
                "http_failed": {
                    "status": "failed", "error_type": "TimeoutError",
                    "availability": {"successes": 2, "failures": 3, "consecutive_failures": 3},
                },
            },
        },
    }


def test_health_snapshot_classifies_http_and_telegram_separately():
    windows = {
        "telegram_good": {
            "completed": 4, "pending": 0, "retry_wait": 0, "quarantined": 0,
            "items_ingested": 50, "updated_at": 1800000000,
        },
        "telegram_retry": {
            "completed": 1, "retry_wait": 2,
            "items_ingested": 1, "updated_at": 1800000010,
        },
    }
    snapshot = build_snapshot(sample_config(), report(), windows, observed_at=1800000020, run_id="123")
    by_id = {item["id"]: item for item in snapshot["sources"]}
    assert by_id["http_ok"]["status"] == "retrieved"
    assert by_id["http_ok"]["http"]["nodes"] == 35
    assert by_id["http_system"]["status"] == "infrastructure_error"
    assert by_id["http_failed"]["status"] == "source_failure"
    assert by_id["http_off"]["status"] == "disabled"
    assert by_id["telegram_good"]["status"] == "observed"
    assert by_id["telegram_retry"]["status"] == "retrying"
    assert by_id["telegram_missing"]["status"] == "not_observed"
    assert by_id["retired"]["status"] == "disabled"
    assert snapshot["counts"]["configured_sources"] == 8
    assert snapshot["counts"]["disabled"] == 2
    assert snapshot["counts"]["http_source_failures"] == 1
    assert snapshot["counts"]["http_infrastructure_errors"] == 1
    assert snapshot["counts"]["telegram_retrying"] == 1
    assert "PRIVATE" not in json.dumps(snapshot)
    assert "HIDDEN" not in json.dumps(snapshot)
    assert "https://" not in json.dumps(snapshot)
    assert snapshot["source_observation_kind"] == "retrieval_and_ingestion_only_not_proxy_health"


def test_missing_queue_data_does_not_get_reported_as_unobserved():
    snapshot = build_snapshot(
        [{"id": "tg", "type": "telegram_user"}], {}, None, observed_at=1800000000
    )
    assert snapshot["sources"][0]["status"] == "evidence_unavailable"
    assert snapshot["queue_evidence_available"] is False


def test_unexpected_http_reports_are_not_allowed_to_invent_sources():
    snapshot = build_snapshot(
        [{"id": "known", "type": "http_subscription", "http_subscription": {"enabled": True}}],
        {"summary": {"http_source_health": {"other": {"status": "parsed", "nodes": 1}}}},
        {}, observed_at=1800000000,
    )
    assert len(snapshot["sources"]) == 1
    assert snapshot["sources"][0]["status"] == "not_observed"


def test_source_status_respects_quarantine_and_preserves_zero_counts():
    snapshot = build_snapshot(
        [{"id": "tg", "type": "telegram_user"}], {},
        {"tg": {"completed": 0, "quarantined": 2, "items_ingested": 0}},
        observed_at=1800000000,
    )
    assert snapshot["sources"][0]["status"] == "quarantined"
    assert snapshot["sources"][0]["windows"]["items_ingested"] == 0


def test_load_queue_evidence_is_scoped_to_current_campaign(tmp_path: Path):
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE ingestion_work_items (campaign_id INTEGER, source_id TEXT, "
            "status TEXT, items_ingested INTEGER, updated_at INTEGER)"
        )
        db.executemany("INSERT INTO ingestion_work_items VALUES (?,?,?,?,?)", [
            (3, "tg", "retry_wait", 10, 100),
            (4, "tg", "completed", 3, 200),
            (4, "tg", "completed", 4, 250),
            (4, "other", "quarantined", 0, 225),
        ])
    summary = load_queue_evidence(db_path, 4)
    assert summary["tg"]["completed"] == 2
    assert summary["tg"]["items_ingested"] == 7
    assert summary["tg"]["updated_at"] == 250
    assert summary["tg"].get("retry_wait", 0) == 0
    assert summary["other"]["quarantined"] == 1
    assert load_queue_evidence(db_path, 0) is None
    assert load_queue_evidence(tmp_path / "missing.db", 4) is None


def test_report_rejects_duplicate_source_ids():
    with pytest.raises(ValueError, match="duplicate"):
        build_snapshot(
            [{"id": "a", "type": "telegram"}, {"id": "a", "type": "telegram"}],
            {}, {}, observed_at=1800000000,
        )


def test_cli_writes_sanitized_json_and_uses_frozen_campaign(tmp_path: Path):
    import subprocess
    import sys

    import yaml

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"sources": sample_config()}), encoding="utf-8")
    health_path = tmp_path / "run-summary.json"
    health_path.write_text(json.dumps(report()), encoding="utf-8")
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE ingestion_work_items (campaign_id INTEGER, source_id TEXT, "
            "status TEXT, items_ingested INTEGER, updated_at INTEGER)"
        )
        db.execute(
            "INSERT INTO ingestion_work_items VALUES "
            "(4, 'telegram_good', 'completed', 12, 1800000000)"
        )
    output = tmp_path / "source-health.json"
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable, str(root / "scripts" / "report_source_health.py"),
            "--config", str(config_path), "--summary", str(health_path),
            "--db", str(db_path), "--output", str(output),
        ], check=True, capture_output=True, text=True,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["queue_campaign_id"] == 4
    assert payload["counts"]["telegram_observed"] == 1
    assert payload["counts"]["http_infrastructure_errors"] == 1
    assert "source-health:" in completed.stdout
    assert "HIDDEN" not in output.read_text(encoding="utf-8")
