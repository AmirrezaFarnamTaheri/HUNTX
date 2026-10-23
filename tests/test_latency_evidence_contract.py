"""TCP endpoint latency is neither proxy authentication nor UDP reachability."""

import asyncio
import base64
import json
import math
import socket
from unittest.mock import AsyncMock, patch

import pytest

from huntx.core.latency_benchmarker import check_proxy_latency, filter_proxies_by_latency


@pytest.mark.asyncio
async def test_vmess_host_is_parsed_from_payload_instead_of_fake_base64_hostname(monkeypatch):
    vmess = {
        "v": "2", "ps": "node", "add": "example.com", "port": "443",
        "id": "11111111-2222-3333-4444-555555555555", "net": "ws", "tls": "tls",
    }
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "getaddrinfo", new_callable=AsyncMock) as resolver,
        patch("asyncio.open_connection", new_callable=AsyncMock) as connect,
    ):
        resolver.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ]
        writer = AsyncMock()
        connect.return_value = (AsyncMock(), writer)
        measurement = await check_proxy_latency(link, timeout=1.0)
    assert measurement is not None and math.isfinite(measurement)
    resolver.assert_awaited_once_with(
        "example.com", 443, type=socket.SOCK_STREAM
    )
    connect.assert_awaited_once_with("8.8.8.8", 443, family=socket.AF_INET)


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", [
    "hysteria2://secret@1.1.1.1:443", "hy2://secret@1.1.1.1:443",
    "tuic://user:pw@1.1.1.1:443",
    "vless://user@1.1.1.1:443?type=quic",
])
async def test_udp_only_links_cannot_be_marked_failed_by_tcp_probe(uri):
    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new_callable=AsyncMock) as resolver:
        assert await check_proxy_latency(uri, timeout=1) is None
        resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_latency_filter_rejects_nan_negative_and_infinite_results_and_labels_tcp():
    records = [
        {"data": {"line": f"vless://user@node{i}.example.com:443"}}
        for i in range(4)
    ]

    async def fake_measure(uri, timeout):
        index = next(i for i in range(4) if f"node{i}." in uri)
        return [float("nan"), -20.0, float("inf"), 35.125][index]

    with (
        patch("huntx.core.latency_benchmarker.check_proxy_latency", side_effect=fake_measure),
        patch("huntx.core.latency_benchmarker.time.time", return_value=1800000000),
    ):
        accepted = await filter_proxies_by_latency(
            records, concurrency=2, max_latency_ms=100, timeout=1.0
        )

    assert len(accepted) == 1
    evidence = accepted[0]["data"]
    assert evidence["latency_ms"] == 35.12 or evidence["latency_ms"] == 35.13
    assert evidence["probe_kind"] == "tcp_connect"
    assert evidence["probe_authenticated"] is False
    assert evidence["probe_checked_at"] == 1800000000
    assert evidence["probe_expires_at"] > evidence["probe_checked_at"]
    assert all("probe_kind" not in source["data"] for source in records)


@pytest.mark.asyncio
async def test_latency_filter_rejects_boolean_probe_result():
    with patch(
        "huntx.core.latency_benchmarker.check_proxy_latency",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await filter_proxies_by_latency(
            [{"data": {"line": "vless://user@example.com:443"}}]
        )
    assert result == []
