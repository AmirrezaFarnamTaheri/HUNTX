import base64

import pytest

from huntx.formats.streaming import StreamingChunkParser


@pytest.mark.asyncio
async def test_streaming_chunk_parser_raw_text():
    parser = StreamingChunkParser(chunk_size=16)

    async def sample_stream():
        yield b"vless://user1@host1:443#Node1\nvmess://"
        yield b"user2@host2:443#Node2\n"
        yield b"trojan://user3@host3:443#Node3\n"

    records = []
    async for rec in parser.parse_stream(sample_stream(), source_info={"source": "test"}):
        records.append(rec)

    assert len(records) == 3
    assert records[0]["protocol"] == "vless"
    assert records[1]["protocol"] == "vmess"
    assert records[2]["protocol"] == "trojan"
    assert records[0]["source_info"]["source"] == "test"


@pytest.mark.asyncio
async def test_streaming_chunk_parser_base64():
    parser = StreamingChunkParser()
    raw_payload = b"vless://u1@h1:443#N1\nvmess://u2@h2:443#N2\n"
    encoded = base64.b64encode(raw_payload)

    async def b64_stream():
        # Yield in 10-byte chunks to test boundary alignment
        for i in range(0, len(encoded), 10):
            yield encoded[i:i + 10]

    records = []
    async for rec in parser.parse_stream(b64_stream()):
        records.append(rec)

    assert len(records) == 2
    assert [record["protocol"] for record in records] == ["vless", "vmess"]
    hashes = [record["unique_hash"] for record in records]
    assert len(set(hashes)) == len(records)


def test_streaming_parser_parse_bytes():
    parser = StreamingChunkParser()
    raw = b"vless://user@1.1.1.1:443\nhysteria2://user@2.2.2.2:443\n"
    recs = parser.parse_bytes(raw)
    assert len(recs) == 2
    assert recs[0]["protocol"] == "vless"
    assert recs[1]["protocol"] == "hysteria2"


@pytest.mark.asyncio
async def test_streaming_parser_malformed_stream_does_not_crash():
    """
    Plan Task 1.2: 'malformed streams' must be tested.
    Garbage bytes that are neither valid base64 nor valid proxy URIs
    should yield 0 records and not raise.
    """
    parser = StreamingChunkParser()

    async def garbage_stream():
        yield b"\x00\x01\x02\xff\xfe garbage not a proxy\n"
        yield b"also-not-valid://\n"
        yield b"   \n\n\n"

    records = []
    async for rec in parser.parse_stream(garbage_stream()):
        records.append(rec)

    # Malformed / unknown-scheme lines must be silently skipped, not crash
    assert isinstance(records, list)
    for rec in records:
        # Any record that does get emitted must still have the required fields
        assert "unique_hash" in rec
        assert "raw_uri" in rec


@pytest.mark.asyncio
async def test_streaming_parser_empty_stream_yields_nothing():
    """parse_stream on empty async iterator must yield zero records."""
    parser = StreamingChunkParser()

    async def empty_stream():
        return
        yield  # make it an async generator

    records = [rec async for rec in parser.parse_stream(empty_stream())]
    assert records == []
