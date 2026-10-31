"""Release independence when Telegram is rate-limited but HTTP produced usable data.

Only verified, retry-only Telegram residue may be advisory. A general partial
run, missing HTTP input, or timeout must still prohibit publication.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


def runner(residue, reports, exhausted=False):
    instance = object.__new__(OptimizedHardenedOrchestrator)
    instance._work_queue = MagicMock()
    instance._work_queue.summary.return_value = residue
    instance._ingestion_budget_exhausted = exhausted
    instance._http_source_reports = reports
    return instance


@pytest.mark.parametrize("environment,expected", [
    ("1", None), ("0", "ingestion_residue_remaining"),
])
def test_telegram_retry_only_does_not_block_verified_http_flow(monkeypatch, environment, expected):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", environment)
    orch = runner({"remaining": 5, "retry_wait": 5},
                  {"feed-a": {"status": "parsed", "nodes": 7}})
    assert orch._ingestion_demotion_reason() == expected


@pytest.mark.parametrize("residue", [
    {"remaining": 5, "retry_wait": 4, "pending": 1},
    {"remaining": 5, "retry_wait": 4, "partial": 1},
    {"remaining": 5, "retry_wait": 4, "leased": 1},
    {"remaining": 5, "retry_wait": "5"},
])
def test_unfinished_nonretry_work_remains_fatal_for_release(monkeypatch, residue):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    orch = runner(residue, {"feed-a": {"status": "parsed", "nodes": 7}})
    assert orch._ingestion_demotion_reason() == "ingestion_residue_remaining"


@pytest.mark.parametrize("reports", [
    {}, {"feed-a": {"status": "failed", "nodes": 9}},
    {"feed-a": {"status": "parsed", "nodes": 0}},
    {"feed-a": {"status": "infrastructure_error", "nodes": 3}},
])
def test_retry_only_needs_verified_current_http_ingestion(monkeypatch, reports):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    orch = runner({"remaining": 5, "retry_wait": 5}, reports)
    assert orch._ingestion_demotion_reason() == "ingestion_residue_remaining"


def test_telegram_backlog_cannot_override_exhausted_global_budget(monkeypatch):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    orch = runner({"remaining": 5, "retry_wait": 5},
                  {"feed-a": {"status": "parsed", "nodes": 1}}, exhausted=True)
    assert orch._ingestion_demotion_reason() == "ingestion_budget_exhausted"


def test_telegram_backlog_normal_run_released_without_special_policy(monkeypatch):
    monkeypatch.delenv("HUNTX_TELEGRAM_RETRY_RELEASE", raising=False)
    orch = runner({"remaining": 5, "retry_wait": 5},
                  {"feed-a": {"status": "parsed", "nodes": 5}})
    assert orch._ingestion_demotion_reason() == "ingestion_residue_remaining"


def test_missing_queue_state_does_not_authorize_release(monkeypatch):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    orch = object.__new__(OptimizedHardenedOrchestrator)
    orch._ingestion_budget_exhausted = False
    assert orch._ingestion_demotion_reason() == "ingestion_state_unavailable"


def test_broken_queue_state_does_not_authorize_release(monkeypatch):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    orch = runner({"remaining": 0, "retry_wait": 0}, {})
    orch._work_queue.summary.side_effect = OSError("corrupt sqlite")
    assert orch._ingestion_demotion_reason() == "ingestion_state_unavailable"
