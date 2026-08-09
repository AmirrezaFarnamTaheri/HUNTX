import asyncio
import sqlite3

from huntx.core.latency_benchmarker import filter_proxies_by_latency
from huntx.core.self_healing import SelfHealingDaemon
from huntx.formats.streaming import StreamingChunkParser


def test_streaming_parser_preserves_split_utf8_multibyte_character():
    parser = StreamingChunkParser()
    payload = "vless://user@host.example:443#Nodé\n".encode("utf-8")
    split_at = payload.index("é".encode("utf-8")) + 1

    async def stream():
        yield payload[:split_at]
        yield payload[split_at:]

    async def collect():
        return [record async for record in parser.parse_stream(stream())]

    records = asyncio.run(collect())
    assert len(records) == 1
    assert records[0]["raw_uri"] == "vless://user@host.example:443#Nodé"


def test_latency_filter_accepts_streaming_parser_byte_records(monkeypatch):
    async def fake_latency(proxy_url: str, timeout: float):
        assert proxy_url == "vless://user@fast.example:443#fast"
        return 25.0

    monkeypatch.setattr(
        "huntx.core.latency_benchmarker.check_proxy_latency",
        fake_latency,
    )
    record = StreamingChunkParser().parse_line("vless://user@fast.example:443#fast")
    assert record is not None

    filtered = asyncio.run(
        filter_proxies_by_latency([record], max_latency_ms=100.0, timeout=1.0)
    )

    assert len(filtered) == 1
    assert filtered[0]["raw_uri"] == record["raw_uri"]
    assert filtered[0]["latency_ms"] == 25.0


def test_file_backed_self_healing_closes_every_opened_connection(tmp_path, monkeypatch):
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        opened = 0
        closed = 0

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            type(self).opened += 1

        def close(self):
            type(self).closed += 1
            super().close()

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)

    daemon = SelfHealingDaemon(db_path=str(tmp_path / "healing.db"), backoff_schedule=[1])
    daemon.record_failure("h1", "vless://user@host.example:443", current_time=0.0)
    assert daemon.get_due_for_retest(current_time=1.0)
    assert daemon.reinstate_proxy("h1") is True

    assert TrackingConnection.opened > 0
    assert TrackingConnection.closed == TrackingConnection.opened
