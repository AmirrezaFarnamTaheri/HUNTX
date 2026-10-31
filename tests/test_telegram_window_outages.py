"""Telegram transport failures are advisory; unexpected bugs remain blocking."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


class FloodWaitError(Exception):
    def __init__(self, seconds):
        super().__init__("opaque Telegram account retry required")
        self.seconds = seconds


def _runtime(error):
    source = SimpleNamespace(
        id="telegram-a",
        type="telegram_user",
        telegram_user=SimpleNamespace(api_id=1, api_hash="private", session="session"),
        required=True,
    )
    item = SimpleNamespace(
        id=10,
        source_id="telegram-a",
        lease_token="lease",
        attempt_count=1,
        window_start_ts=0,
        window_end_ts=3600,
    )
    orch = object.__new__(OptimizedHardenedOrchestrator)
    orch._work_queue = MagicMock()
    orch._work_queue.claim_next.side_effect = [item, None]
    orch._source_by_id = {"telegram-a": source}
    orch._windowed_ingestion = SimpleNamespace(run_page=AsyncMock(side_effect=error))
    orch._remaining_ingestion_budget = lambda: None
    orch._window_page_size = lambda: 100
    orch._run_owner = "test-owner"
    orch._window_failures = 0
    orch._sources_checked = set()
    return orch


@pytest.mark.parametrize(
    ("opt_in", "required_failures", "availability_failures"),
    [("0", 1, 0), ("1", 0, 1)],
)
def test_floodwait_is_nonblocking_only_under_explicit_policy(
    monkeypatch, opt_in, required_failures, availability_failures,
):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", opt_in)
    orch = _runtime(FloodWaitError(15))
    results = {"ok": 0, "err": 0}

    asyncio.run(orch._run_persistent_windows(results, asyncio.Lock(), 3.0))

    assert results["err"] == required_failures
    assert results.get("optional_err", 0) == availability_failures
    assert orch._window_failures == 1
    orch._work_queue.defer_sources.assert_called_once()


@pytest.mark.parametrize(
    ("opt_in", "required_failures", "availability_failures"),
    [("0", 1, 0), ("1", 0, 1)],
)
def test_source_timeout_is_advisory_only_if_global_budget_is_intact(
    monkeypatch, opt_in, required_failures, availability_failures,
):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", opt_in)
    orch = _runtime(asyncio.TimeoutError("temporary transport timeout"))
    results = {"ok": 0, "err": 0}
    asyncio.run(orch._run_persistent_windows(results, asyncio.Lock(), 3.0))
    assert results["err"] == required_failures
    assert results.get("optional_err", 0) == availability_failures
    orch._work_queue.fail.assert_called_once()


def test_unrecognized_window_exception_is_never_forgiven_or_logged_verbatim(
    monkeypatch, caplog,
):
    monkeypatch.setenv("HUNTX_TELEGRAM_RETRY_RELEASE", "1")
    secret = "super-secret-session-string"
    orch = _runtime(RuntimeError(secret))
    results = {"ok": 0, "err": 0}

    asyncio.run(orch._run_persistent_windows(results, asyncio.Lock(), 3.0))

    assert results["err"] == 1
    assert results.get("optional_err", 0) == 0
    saved_reason = str(orch._work_queue.fail.call_args.args[2])
    assert secret not in saved_reason
    assert secret not in caplog.text
