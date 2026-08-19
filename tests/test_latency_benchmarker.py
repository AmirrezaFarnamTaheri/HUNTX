import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, patch

from huntx.core.latency_benchmarker import (
    _public_addresses,
    check_proxy_latency,
    filter_proxies_by_latency,
)


class TestLatencyBenchmarker(unittest.TestCase):
    def test_check_proxy_latency_invalid_url(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(check_proxy_latency("invalid_url_no_port"))
            self.assertIsNone(result)
        finally:
            loop.close()

    def test_private_and_loopback_resolutions_are_rejected(self):
        infos = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.1.2", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        ]

        self.assertEqual(_public_addresses(infos), [(socket.AF_INET, "8.8.8.8")])

    @patch("asyncio.open_connection")
    def test_check_proxy_latency_success(self, mock_open_conn):
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_open_conn.return_value = (mock_reader, mock_writer)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.getaddrinfo = AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
            ]
        )
        try:
            latency = loop.run_until_complete(
                check_proxy_latency("vless://user@example.com:443?type=ws#test", timeout=1.0)
            )
            self.assertIsNotNone(latency)
            self.assertGreaterEqual(latency, 0)
            mock_open_conn.assert_awaited_once_with(
                "8.8.8.8",
                443,
                family=socket.AF_INET,
            )
        finally:
            loop.close()

    @patch("asyncio.open_connection")
    def test_check_proxy_latency_never_connects_to_private_dns_answer(self, mock_open_conn):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.getaddrinfo = AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443)),
            ]
        )
        try:
            result = loop.run_until_complete(
                check_proxy_latency("vless://user@attacker.example:443", timeout=1.0)
            )
            self.assertIsNone(result)
            mock_open_conn.assert_not_awaited()
        finally:
            loop.close()

    @patch("huntx.core.latency_benchmarker.check_proxy_latency")
    def test_filter_proxies_by_latency(self, mock_check_latency):
        async def mock_latency(url, timeout):
            if "fast" in url:
                return 150.0
            if "slow" in url:
                return 4000.0
            return None

        mock_check_latency.side_effect = mock_latency

        proxies = [
            {"data": {"line": "vless://user@fast.com:443#fast"}},
            {"data": {"line": "vless://user@slow.com:443#slow"}},
            {"data": {"line": "vless://user@dead.com:443#dead"}},
        ]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            filtered = loop.run_until_complete(
                filter_proxies_by_latency(
                    proxies,
                    max_latency_ms=3000.0,
                    timeout=1.0,
                )
            )
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["data"]["line"], "vless://user@fast.com:443#fast")
            self.assertEqual(filtered[0]["data"]["latency_ms"], 150.0)
        finally:
            loop.close()
