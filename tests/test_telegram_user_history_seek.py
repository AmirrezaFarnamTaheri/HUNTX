"""Server-side Telegram date seeks preserve cursor semantics while avoiding full-history scans."""
from collections import defaultdict
from datetime import datetime, timezone

import pytest

from huntx.connectors.telegram_user.connector import TelegramUserConnector


class RecordingTelegramHistory:
    def __init__(self):
        self.calls = []

    def iter_messages(self, peer, **kwargs):
        self.calls.append((peer, kwargs))

        async def nothing():
            if False:
                yield None

        return nothing()


async def collect(iterator):
    return [message async for message in iterator]


@pytest.mark.asyncio
async def test_new_telegram_source_seeks_to_freshness_window_server_side():
    connector = TelegramUserConnector(1, "hash", "session", "@new_group")
    client = RecordingTelegramHistory()
    cutoff = 1763770000.5

    assert await collect(connector._fetch_text_pass(
        client, "peer", 0, cutoff, defaultdict(int),
    )) == []
    assert await collect(connector._fetch_document_pass(
        client, "peer", 0, cutoff, defaultdict(int),
    )) == []

    assert len(client.calls) == 2
    for peer, kwargs in client.calls:
        assert peer == "peer"
        assert kwargs["min_id"] == 0
        assert kwargs["reverse"] is True
        assert kwargs["offset_date"] == datetime.fromtimestamp(
            cutoff - 1, tz=timezone.utc,
        )
    assert "filter" not in client.calls[0][1]
    assert "filter" in client.calls[1][1]


@pytest.mark.asyncio
async def test_reconnecting_or_subsequent_cursors_use_ids_not_date_seek():
    connector = TelegramUserConnector(1, "hash", "session", "@old_group")
    client = RecordingTelegramHistory()

    assert await collect(connector._fetch_text_pass(
        client, "peer", 42, 1763770000.5, defaultdict(int),
    )) == []
    assert await collect(connector._fetch_document_pass(
        client, "peer", 56, 1763770000.5, defaultdict(int),
    )) == []
    assert [(call[1]["min_id"], call[1]["reverse"]) for call in client.calls] == [
        (42, True), (56, True),
    ]
    assert all("offset_date" not in call[1] for call in client.calls)


@pytest.mark.asyncio
async def test_telegram_unbounded_backfill_does_not_enable_date_seek():
    connector = TelegramUserConnector(1, "hash", "session", "@archive_group")
    client = RecordingTelegramHistory()

    assert await collect(connector._fetch_text_pass(
        client, "peer", 0, 0, defaultdict(int),
    )) == []
    assert await collect(connector._fetch_document_pass(
        client, "peer", 0, 0, defaultdict(int),
    )) == []
    assert all("offset_date" not in call[1] for call in client.calls)
