"""Flood waits are MTProto account cooldowns, not hundreds of bad windows."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from huntx.connectors.telegram_user.failure_policy import (
    is_permanent_telegram_peer_error,
    telegram_account_key,
    telegram_flood_wait_seconds,
)
from huntx.core import runtime_resilience
from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator
from huntx.state.db import open_db
from huntx.state.ingestion_queue import PersistentIngestionQueue


class FloodWaitError(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Telegram asked to wait {seconds} seconds")


def _source(name: str, session: str = "shared"):
    return SimpleNamespace(
        id=name, type="telegram_user",
        telegram_user=SimpleNamespace(
            api_id=123, api_hash="secret-api-hash",
            session=session, peer="@" + name,
        ),
    )


def test_flood_wait_detection_is_typed_and_follows_nested_causes():
    error = FloodWaitError(6011)
    assert telegram_flood_wait_seconds(error) == 6011
    assert not is_permanent_telegram_peer_error(error)
    try:
        raise ValueError("wrapped transport exception") from error
    except ValueError as wrapped:
        assert telegram_flood_wait_seconds(wrapped) == 6011
    assert telegram_flood_wait_seconds(ValueError("FloodWaitError 6000")) is None
    assert telegram_flood_wait_seconds(FloodWaitError(-10)) is None
    assert telegram_flood_wait_seconds(FloodWaitError(0)) is None
    assert telegram_account_key(_source("a")) == telegram_account_key(_source("b"))
    assert telegram_account_key(_source("a")) != telegram_account_key(_source("c", "separate"))


def test_session_cooldown_defers_only_its_own_windows_and_survives_new_seed(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    sources = [_source("a"), _source("b"), _source("c", "separate")]
    queue.seed_rolling_horizon(
        sources, now=10_000, lookback_seconds=3600, window_seconds=3600,
    )
    assert queue.defer_sources(["a", "b"], now=10_000, retry_delay=6011) == 2

    independent = queue.claim_next("run", lease_seconds=60, now=10_001)
    assert independent is not None and independent.source_id == "c"

    # A new rolling hour must inherit the existing account cooldown. It may
    # not slip through merely because its work item was created later.
    queue.seed_rolling_horizon(
        sources, now=14_000, lookback_seconds=3600, window_seconds=3600,
    )
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT source_id, status, next_retry_at FROM ingestion_work_items "
            "WHERE source_id IN ('a', 'b')",
        ).fetchall()
    assert len(rows) == 4
    assert all(row["status"] == "retry_wait" for row in rows)
    assert all(row["next_retry_at"] >= 16_011 for row in rows)
    assert queue.summary()["remaining"] == 6

    due = queue.claim_next("next", lease_seconds=60, now=16_012)
    assert due is not None and due.source_id in {"a", "b"}


@pytest.mark.asyncio
async def test_flood_wait_on_one_window_postpones_same_account_without_hot_loop(tmp_path):
    queue = PersistentIngestionQueue(open_db(tmp_path / "state.db"))
    now = int(time.time())
    sources = [_source("a"), _source("b")]
    queue.seed_rolling_horizon(
        sources, now=now, lookback_seconds=3600, window_seconds=3600,
    )
    runner = object.__new__(OptimizedHardenedOrchestrator)
    runner._work_queue = queue
    runner._source_by_id = {str(source.id): source for source in sources}
    runner._run_owner = "current"
    runner._windowed_ingestion = SimpleNamespace(
        run_page=AsyncMock(side_effect=FloodWaitError(6011)),
    )
    runner._remaining_ingestion_budget = lambda: None
    runner._window_page_size = lambda: 50
    runner._window_failures = 0
    runner._window_pages = 0
    runner._window_completions = 0
    runner._sources_checked = set()
    runner._messages_scanned = 0
    runner._messages_new = 0
    runner._cursor_updates = 0
    results = {"ok": 0, "err": 0}

    await runner._run_persistent_windows(results, asyncio.Lock(), 30.0)

    assert results == {"ok": 0, "err": 1}
    assert runner._window_failures == 1
    runner._windowed_ingestion.run_page.assert_awaited_once()
    with queue.db.connect() as conn:
        rows = conn.execute(
            "SELECT source_id, status, next_retry_at, continuation_cursor, "
            "last_error FROM ingestion_work_items",
        ).fetchall()
    assert len(rows) == 2
    assert all(row["status"] == "retry_wait" for row in rows)
    assert all(row["next_retry_at"] > now + 6000 for row in rows)
    assert all(row["continuation_cursor"] is None for row in rows)
    assert all(row["last_error"] == "Telegram shared FloodWait cooldown" for row in rows)


@pytest.mark.asyncio
async def test_canonical_preflight_stops_resolving_rate_limited_account():
    sources = [_source("a"), _source("b")]
    queue = MagicMock()
    queue.defer_sources.return_value = 2
    runner = SimpleNamespace(
        _work_queue=queue, _ingestion_stop_monotonic=None,
        _ingestion_budget_exhausted=False,
    )

    class RateLimitedConnector:
        attempts = 0

        def __init__(self, **kwargs):
            self.peer = kwargs["peer"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_channel_id_async(self):
            type(self).attempts += 1
            raise FloodWaitError(6011)

    with patch.object(
        runtime_resilience.optimized_module,
        "WindowedTelegramUserConnector",
        RateLimitedConnector,
    ):
        accepted = await runtime_resilience._canonical_ingestion_sources(
            runner, sources,
        )

    assert [source.id for source in accepted] == ["a", "b"]
    assert RateLimitedConnector.attempts == 1
    queue.terminalize_source.assert_not_called()
    queue.defer_sources.assert_called_once()
    assert set(queue.defer_sources.call_args.args[0]) == {"a", "b"}
    assert list(runner._preflight_flood_deadlines.values())[0] > time.time()
