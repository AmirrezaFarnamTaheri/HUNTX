from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from huntx.connectors.telegram_user.connector import TelegramUserConnector
from huntx.core import runtime_resilience
from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


class PeerIdInvalidError(Exception):
    pass


def _window_failure_orchestrator(exc: Exception):
    item = SimpleNamespace(
        id=11,
        source_id="dead-source",
        window_start_ts=100,
        window_end_ts=200,
        continuation_cursor=None,
        attempt_count=1,
        lease_token="lease-token",
    )
    queue = MagicMock()
    queue.claim_next.side_effect = [item, None]

    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._run_owner = "run-owner"
    orchestrator._source_by_id = {
        "dead-source": SimpleNamespace(
            id="dead-source",
            type="telegram_user",
            telegram_user=object(),
        )
    }
    orchestrator._work_queue = queue
    orchestrator._windowed_ingestion = SimpleNamespace(
        run_page=AsyncMock(side_effect=exc),
    )
    orchestrator._window_failures = 0
    orchestrator._window_pages = 0
    orchestrator._window_completions = 0
    orchestrator._sources_checked = set()
    orchestrator._messages_scanned = 0
    orchestrator._messages_new = 0
    orchestrator._cursor_updates = 0
    orchestrator._remaining_ingestion_budget = lambda: None
    orchestrator._window_page_size = lambda: 100
    return orchestrator, queue


@pytest.mark.asyncio
async def test_dead_username_terminalizes_all_source_windows_instead_of_retrying():
    orchestrator, queue = _window_failure_orchestrator(
        ValueError('No user has "sip_socksip" as username')
    )
    results = {"ok": 0, "err": 0}

    await orchestrator._run_persistent_windows(results, asyncio.Lock(), 30.0)

    queue.terminalize_source.assert_called_once()
    assert queue.terminalize_source.call_args.args[0] == "dead-source"
    queue.fail.assert_not_called()
    assert results == {"ok": 0, "err": 1}


@pytest.mark.asyncio
async def test_unusable_numeric_peer_terminalizes_source_instead_of_retrying():
    orchestrator, queue = _window_failure_orchestrator(
        ValueError(
            "Could not find the input entity for "
            "PeerChannel(channel_id=2272946873) (PeerChannel)"
        )
    )
    results = {"ok": 0, "err": 0}

    await orchestrator._run_persistent_windows(results, asyncio.Lock(), 30.0)

    queue.terminalize_source.assert_called_once()
    assert queue.terminalize_source.call_args.args[0] == "dead-source"
    queue.fail.assert_not_called()
    assert results == {"ok": 0, "err": 1}


@pytest.mark.asyncio
async def test_peer_id_invalid_terminalizes_source_instead_of_retrying():
    orchestrator, queue = _window_failure_orchestrator(
        PeerIdInvalidError("An invalid Peer was used")
    )
    results = {"ok": 0, "err": 0}

    await orchestrator._run_persistent_windows(results, asyncio.Lock(), 30.0)

    queue.terminalize_source.assert_called_once()
    assert queue.terminalize_source.call_args.args[0] == "dead-source"
    queue.fail.assert_not_called()
    assert results == {"ok": 0, "err": 1}


@pytest.mark.asyncio
async def test_transient_window_failure_remains_retryable():
    orchestrator, queue = _window_failure_orchestrator(
        ConnectionError("temporary Telegram transport failure")
    )
    results = {"ok": 0, "err": 0}

    await orchestrator._run_persistent_windows(results, asyncio.Lock(), 30.0)

    queue.terminalize_source.assert_not_called()
    queue.fail.assert_called_once()
    assert queue.fail.call_args.args[:3] == (
        11,
        "run-owner",
        "temporary Telegram transport failure",
    )
    assert results == {"ok": 0, "err": 1}


@pytest.mark.asyncio
async def test_numeric_peer_is_reachability_checked_during_canonical_preflight():
    source = SimpleNamespace(
        id="src_1002272946873",
        type="telegram_user",
        telegram_user=SimpleNamespace(
            api_id=123,
            api_hash="hash",
            session="session",
            peer="-1002272946873",
        ),
    )
    queue = MagicMock()
    queue.terminalize_source.return_value = 48
    orchestrator = SimpleNamespace(
        _work_queue=queue,
        _ingestion_stop_monotonic=None,
        _ingestion_budget_exhausted=False,
    )

    class UnavailableNumericConnector:
        def __init__(self, **kwargs):
            self.peer = kwargs["peer"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_channel_id_async(self):
            raise ValueError(
                "Could not find the input entity for "
                "PeerChannel(channel_id=2272946873) (PeerChannel)"
            )

    with patch.object(
        runtime_resilience.optimized_module,
        "WindowedTelegramUserConnector",
        UnavailableNumericConnector,
    ):
        accepted = await runtime_resilience._canonical_ingestion_sources(
            orchestrator,
            [source],
        )

    assert accepted == []
    queue.terminalize_source.assert_called_once()
    assert queue.terminalize_source.call_args.args[0] == source.id


@pytest.mark.asyncio
async def test_strict_channel_resolution_surfaces_transient_lookup_failure():
    connector = TelegramUserConnector(123, "hash", "session", "-10042")
    client = MagicMock()
    client.is_connected.return_value = True
    client.get_entity = AsyncMock(side_effect=ConnectionError("temporary lookup failure"))

    with patch.object(connector, "_client", return_value=client):
        with pytest.raises(ConnectionError, match="temporary lookup failure"):
            await connector.resolve_channel_id_strict_async()
