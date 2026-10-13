"""Recovery-aware public address probes never convert one failed IP into a dead proxy."""
from __future__ import annotations

import math
import socket
import ssl
from unittest.mock import AsyncMock, Mock

import pytest

from huntx.core.network_diagnostics import inspect_target


def _target(**changes):
    target = {
        "endpoint_id": "a" * 24,
        "protocol": "vless",
        "host": "multi.example.net",
        "host_kind": "dns_name",
        "port": 443,
        "transport_kind": "tcp",
        "transport": "ws",
        "tls_mode": "none",
    }
    target.update(changes)
    return target


def _dual_stack():
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
    ]


@pytest.mark.asyncio
async def test_ipv4_connect_failure_falls_back_to_ipv6_without_claiming_proxy_authentication():
    writer = Mock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()
    resolver = AsyncMock(return_value=_dual_stack())
    connector = AsyncMock(side_effect=[OSError("unreachable"), (Mock(), writer)])
    result = await inspect_target(
        _target(), resolver=resolver, connector=connector, timeout=1.5
    )
    assert connector.await_count == 2
    assert connector.await_args_list[0].args[0] == "1.1.1.1"
    assert connector.await_args_list[1].args[0] == "2606:4700:4700::1111"
    assert result["tcp"]["status"] == "connected"
    assert result["tcp"]["attempts"] == 2
    assert result["tcp"]["ip_family"] == "ipv6"
    assert result["proxy_protocol"]["status"] == "unverified"
    assert result["terminal"] is False
    assert "unreachable" not in str(result)
    assert "1.1.1.1" not in str(result)


@pytest.mark.asyncio
async def test_tls_certificate_failure_on_one_address_can_recover_on_another():
    writer = Mock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()
    tls = Mock()
    tls.version.return_value = "TLSv1.3"
    tls.selected_alpn_protocol.return_value = "h2"
    writer.get_extra_info.return_value = tls
    connector = AsyncMock(side_effect=[
        ssl.SSLCertVerificationError("bad certificate"),
        (Mock(), writer),
    ])
    result = await inspect_target(
        _target(tls_mode="tls"), resolver=AsyncMock(return_value=_dual_stack()),
        connector=connector, timeout=1.5,
    )
    assert connector.await_count == 2
    assert result["tcp"]["status"] == "connected"
    assert result["tls"]["status"] == "verified_handshake"
    assert result["tls"]["verified_hostname"] is True
    assert result["tls"]["version"] == "TLSv1.3"
    assert result["proxy_protocol"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_all_failures_remain_recoverable_and_report_attempt_count():
    result = await inspect_target(
        _target(),
        resolver=AsyncMock(return_value=_dual_stack()),
        connector=AsyncMock(side_effect=ConnectionRefusedError("refused")),
        timeout=1.5,
    )
    assert result["tcp"]["status"] == "connect_failed"
    assert result["tcp"]["attempts"] == 2
    assert result["terminal"] is False
    assert result["next_action"] == "retry_tcp_from_independent_vantage"


@pytest.mark.asyncio
async def test_dns_and_tcp_elapsed_metrics_are_finite_and_not_auth_metrics():
    writer = Mock(close=Mock(), wait_closed=AsyncMock())
    result = await inspect_target(
        _target(), resolver=AsyncMock(return_value=_dual_stack()),
        connector=AsyncMock(return_value=(Mock(), writer)), timeout=1.5,
    )
    assert math.isfinite(result["dns"]["elapsed_ms"])
    assert math.isfinite(result["tcp"]["elapsed_ms"])
    assert 0 <= result["dns"]["elapsed_ms"] <= 1500
    assert 0 <= result["tcp"]["elapsed_ms"] <= 1500
    assert result["proxy_protocol"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_udp_protocol_still_skips_tcp_and_tls_with_no_false_failure():
    connector = AsyncMock()
    result = await inspect_target(
        _target(protocol="hysteria2", transport_kind="udp"),
        resolver=AsyncMock(return_value=_dual_stack()),
        connector=connector,
    )
    assert result["tcp"]["status"] == "not_applicable_udp"
    connector.assert_not_awaited()


@pytest.mark.asyncio
async def test_many_ipv4_routes_cannot_starve_reachable_ipv6_with_four_attempt_cap():
    """Regression: 4+ A records must never consume the entire bounded budget."""
    many_ipv4_and_one_ipv6 = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
        for ip in ("8.8.8.8", "1.1.1.1", "9.9.9.9", "8.8.4.4", "1.0.0.1")
    ] + [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
    ]
    writer = Mock(close=Mock(), wait_closed=AsyncMock())

    async def dial(address, port, **options):
        if options["family"] == socket.AF_INET:
            raise OSError("IPv4 route unavailable")
        return Mock(), writer

    connector = AsyncMock(side_effect=dial)
    result = await inspect_target(
        _target(), resolver=AsyncMock(return_value=many_ipv4_and_one_ipv6),
        connector=connector, timeout=2.0,
    )
    assert result["dns"]["ipv4_count"] == 5
    assert result["dns"]["ipv6_count"] == 1
    assert result["tcp"]["status"] == "connected"
    assert result["tcp"]["ip_family"] == "ipv6"
    assert result["tcp"]["attempts"] == 2
    assert connector.await_count == 2
    assert connector.await_args_list[0].kwargs["family"] == socket.AF_INET
    assert connector.await_args_list[1].kwargs["family"] == socket.AF_INET6
    assert result["proxy_protocol"]["status"] == "unverified"
    assert result["terminal"] is False


@pytest.mark.asyncio
async def test_attempt_cap_is_four_and_includes_both_address_families_when_all_fail():
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
        for ip in ("8.8.8.8", "1.1.1.1", "9.9.9.9", "8.8.4.4", "1.0.0.1")
    ] + [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0))
        for ip in ("2606:4700:4700::1111", "2606:4700:4700::1001")
    ]
    connector = AsyncMock(side_effect=ConnectionRefusedError("network down"))
    result = await inspect_target(
        _target(), resolver=AsyncMock(return_value=addresses), connector=connector,
        timeout=2.0,
    )
    assert connector.await_count == 4
    assert [call.kwargs["family"] for call in connector.await_args_list] == [
        socket.AF_INET, socket.AF_INET6, socket.AF_INET, socket.AF_INET6,
    ]
    assert result["tcp"]["status"] == "connect_failed"
    assert result["tcp"]["attempts"] == 4
    assert result["terminal"] is False
