from __future__ import annotations

import asyncio
import datetime
import hashlib
from types import SimpleNamespace

import pytest

import huntx.cli.main as cli_main_module
from huntx.config.validate import _configured_publish_token
from huntx.connectors.telegram_user.windowed import WindowedTelegramUserConnector
from huntx.pipeline.publish import PublishPipeline
from huntx.state.db import open_db
from huntx.state.repo import StateRepo


class MessageMediaWebPage:
    """Test double deliberately named like Telethon's non-downloadable preview media."""


class _AsyncMessages:
    def __init__(self, messages):
        self.messages = messages

    def __aiter__(self):
        async def generate():
            for message in self.messages:
                yield message

        return generate()


class _PreviewClient:
    def __init__(self, message):
        self.message = message
        self.download_calls = 0

    def iter_messages(self, peer, **kwargs):
        return _AsyncMessages([self.message])

    def iter_download(self, media, request_size):
        self.download_calls += 1
        raise AssertionError("webpage previews must never reach iter_download")


class _WindowConnector(WindowedTelegramUserConnector):
    def __init__(self, client):
        self._fake_client = client
        self.peer = "peer"

    def _client(self):
        return self._fake_client

    async def _ensure_connected_async(self, client):
        return None

    async def _resolve_peer_async(self, peer_entity, client=None):
        return peer_entity


def test_windowed_ingestion_keeps_webpage_text_without_downloading_preview():
    timestamp = 4_500
    message = SimpleNamespace(
        id=42,
        date=datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc),
        message="https://example.invalid/config",
        document=object(),
        media=MessageMediaWebPage(),
        file=SimpleNamespace(name="preview.bin", ext=".bin", size=123),
        photo=None,
        video=None,
        gif=None,
        sticker=None,
        voice=None,
        audio=None,
        video_note=None,
    )
    client = _PreviewClient(message)
    connector = _WindowConnector(client)

    page = asyncio.run(
        connector.fetch_window_page(
            window_start_ts=4_000,
            window_end_ts=5_000,
            continuation_cursor=None,
            limit=10,
        )
    )

    assert page.completed
    assert page.scanned_messages == 1
    assert [item.external_id for item in page.items] == ["42"]
    assert page.items[0].data == b"https://example.invalid/config"
    assert client.download_calls == 0


def test_publish_pipeline_never_falls_back_to_ingestion_bot_token(monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLISH_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "ingestion-token")
    payload = b"proxy-config\n"
    build_result = {
        "route_name": "all",
        "unique_id": "all:conf_lines",
        "format": "conf_lines",
        "data": payload,
        "artifact_hash": hashlib.sha256(payload).hexdigest(),
    }
    pipeline = PublishPipeline(StateRepo(open_db(tmp_path / "state.db")))

    with pytest.raises(RuntimeError, match="No token configured"):
        pipeline.run(
            build_result,
            [{"chat_id": "123", "mode": "post_on_change", "required": True}],
        )

    assert pipeline.publishers == {}


def test_config_validation_never_falls_back_to_ingestion_bot_token(monkeypatch):
    monkeypatch.delenv("PUBLISH_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "ingestion-token")

    assert _configured_publish_token(None) is None
    assert _configured_publish_token("destination-token") == "destination-token"

    monkeypatch.setenv("PUBLISH_BOT_TOKEN", "publisher-token")
    assert _configured_publish_token(None) == "publisher-token"


def test_auto_delivery_does_not_reuse_ingestion_token(monkeypatch):
    monkeypatch.delenv("PUBLISH_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "ingestion-token")
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")

    # Missing dedicated publisher credentials must be a safe no-op rather than
    # starting a second getUpdates consumer with TELEGRAM_TOKEN.
    cli_main_module._deliver_updates()
