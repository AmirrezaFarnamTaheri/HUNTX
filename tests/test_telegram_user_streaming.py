from __future__ import annotations

import pytest

from huntx.connectors.telegram_user.connector import download_media_bounded


class _Stream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def close(self):
        self.closed = True


class _Client:
    def __init__(self, chunks):
        self.stream = _Stream(chunks)
        self.request_size = None

    def iter_download(self, media, *, request_size):
        assert media == "media"
        self.request_size = request_size
        return self.stream


@pytest.mark.asyncio
async def test_mtproto_download_is_streamed_and_closed():
    client = _Client([b"abc", memoryview(b"def")])

    assert await download_media_bounded(client, "media") == b"abcdef"
    assert client.request_size == 64 * 1024
    assert client.stream.closed is True


@pytest.mark.asyncio
async def test_mtproto_download_stops_before_exceeding_cap(monkeypatch):
    from huntx.connectors.telegram_user import connector

    monkeypatch.setattr(connector, "MAX_DOWNLOAD_BYTES", 5)
    client = _Client([b"123", b"456", b"unreachable"])

    assert await download_media_bounded(client, "media") is None
    assert client.stream.closed is True
    assert client.stream._chunks == [b"unreachable"]
