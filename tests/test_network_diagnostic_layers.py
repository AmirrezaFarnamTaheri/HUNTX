"""Layered DNS/TCP/TLS observations are not proxy-authentication evidence."""
from __future__ import annotations

import asyncio
import socket
import ssl
from unittest.mock import AsyncMock, Mock

import pytest

from huntx.core.network_diagnostics import (
    classify_network_issue,
    inspect_target,
    select_diagnostic_targets,
)


def endpoint(**overrides):
    base = {
        "endpoint_id": "e" * 24,
        "host": "sample.example.com",
        "host_kind": "dns_name",
        "ip": None,
        "port": 443,
        "protocol": "vless",
        "transport_kind": "tcp",
        "transport": "ws",
        "tls_mode": "none",
    }
    base.update(overrides)
    return base


def public_addresses():
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
    ]


@pytest.mark.asyncio
async def test_dns_and_tcp_pin_a_public_numeric_address_without_exposing_it():
    resolver = AsyncMock(return_value=public_addresses())
    writer = Mock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()
    connector = AsyncMock(return_value=(Mock(), writer))
    result = await inspect_target(
        endpoint(), resolver=resolver, connector=connector,
        timeout=1.0, observed_at=1_800_000_000,
    )
    assert result["dns"]["status"] == "resolved_public"
    assert result["dns"]["ipv4_count"] == 1
    assert result["dns"]["ipv6_count"] == 1
    assert result["tcp"]["status"] == "connected"
    assert result["tls"]["status"] == "not_configured"
    assert result["proxy_protocol"]["status"] == "unverified"
    assert result["transport_protocol"]["status"] == "unverified"
    resolver.assert_awaited_once_with(
        "sample.example.com", 443, type=socket.SOCK_STREAM
    )
    destination = connector.await_args.args[0]
    assert destination == "1.1.1.1"
    assert "sample.example.com" not in str(result)
    assert "1.1.1.1" not in str(result)
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_dns_nonpublic_answers_block_any_connection():
    resolver = AsyncMock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
    ])
    connector = AsyncMock()
    result = await inspect_target(endpoint(), resolver=resolver, connector=connector)
    assert result["dns"]["status"] == "no_public_addresses"
    assert result["tcp"]["status"] == "not_attempted"
    connector.assert_not_awaited()


@pytest.mark.asyncio
async def test_dns_timeout_cannot_be_labeled_as_dead():
    resolver = AsyncMock(side_effect=TimeoutError())
    result = await inspect_target(endpoint(), resolver=resolver, connector=AsyncMock())
    assert result["dns"]["status"] == "timeout"
    assert result["disposition"] == "recoverable"
    assert result["terminal"] is False
    assert result["next_action"] == "retry_dns_from_independent_resolvers"


@pytest.mark.asyncio
async def test_dns_no_data_is_not_assumed_to_be_nxdomain():
    resolver = AsyncMock(side_effect=socket.gaierror(socket.EAI_NONAME, "bad"))
    result = await inspect_target(endpoint(), resolver=resolver, connector=AsyncMock())
    assert result["dns"]["status"] == "no_data_or_name_error"
    assert result["terminal"] is False


@pytest.mark.asyncio
async def test_quic_udp_transport_skips_misleading_tcp_or_tls_test():
    resolver = AsyncMock(return_value=public_addresses())
    connector = AsyncMock()
    result = await inspect_target(
        endpoint(transport_kind="udp", protocol="hysteria2", transport="quic"),
        resolver=resolver, connector=connector,
    )
    assert result["dns"]["status"] == "resolved_public"
    assert result["tcp"]["status"] == "not_applicable_udp"
    assert result["tls"]["status"] == "not_applicable_udp"
    connector.assert_not_awaited()


@pytest.mark.asyncio
async def test_tls_certificate_validation_is_enabled_and_kept_separate_from_auth():
    resolver = AsyncMock(return_value=public_addresses())
    writer = Mock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()
    secure = Mock()
    secure.version.return_value = "TLSv1.3"
    secure.selected_alpn_protocol.return_value = "h2"
    secure.cipher.return_value = ("TLS_AES_128_GCM_SHA256", "TLSv1.3", 128)
    secure.getpeercert.return_value = {}
    writer.get_extra_info.return_value = secure
    connector = AsyncMock(return_value=(Mock(), writer))
    result = await inspect_target(
        endpoint(tls_mode="tls", transport="grpc"), resolver=resolver,
        connector=connector, timeout=1.0,
    )
    assert result["tcp"]["status"] == "connected"
    assert result["tls"]["status"] == "verified_handshake"
    assert result["tls"]["version"] == "TLSv1.3"
    assert result["tls"]["alpn"] == "h2"
    assert result["proxy_protocol"]["status"] == "unverified"
    assert result["transport_protocol"]["status"] == "unverified"
    assert connector.await_args.kwargs["ssl"].check_hostname is True
    assert connector.await_args.kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert connector.await_args.kwargs["server_hostname"] == "sample.example.com"


@pytest.mark.asyncio
async def test_reality_is_not_tested_with_plain_tls_hello():
    resolver = AsyncMock(return_value=public_addresses())
    connector = AsyncMock(return_value=(Mock(), Mock(
        close=Mock(), wait_closed=AsyncMock()
    )))
    result = await inspect_target(
        endpoint(tls_mode="reality"), resolver=resolver, connector=connector,
    )
    assert result["tls"]["status"] == "requires_protocol_specific_probe"
    assert connector.await_args.kwargs.get("ssl") is None


@pytest.mark.asyncio
async def test_certificate_verification_failure_is_recoverable_not_terminal():
    resolver = AsyncMock(return_value=public_addresses())
    connector = AsyncMock(side_effect=ssl.SSLCertVerificationError("bad certificate"))
    result = await inspect_target(
        endpoint(tls_mode="tls"), resolver=resolver, connector=connector,
    )
    assert result["tls"]["status"] == "certificate_verification_failed"
    assert result["disposition"] == "recoverable"
    assert result["terminal"] is False
    assert result["next_action"] == "inspect_sni_certificate_chain_and_clock"


@pytest.mark.asyncio
async def test_nonpublic_literal_cannot_be_probed_even_if_metadata_claims_public():
    connector = AsyncMock()
    result = await inspect_target(
        endpoint(host="10.0.0.1", host_kind="public_ip_literal", ip="10.0.0.1"),
        connector=connector,
    )
    assert result["dns"]["status"] == "non_public_literal"
    connector.assert_not_awaited()


def test_recovery_policy_never_permanently_drops_soft_errors():
    soft = (
        "dns_timeout", "dns_no_data_or_name_error", "tcp_refused",
        "tcp_timeout", "tls_certificate_verification_failed",
        "tls_handshake_error", "transport_unsupported",
        "reality_requires_native_probe", "protocol_auth_failed",
        "source_unavailable", "expired_evidence", "ip_family_mismatch",
        "cdn_fronting_unknown", "tls_insecure_configured",
    )
    assert all(classify_network_issue(code)["terminal"] is False for code in soft)


def test_deterministic_sampling_is_diverse_bounded_and_repeatable():
    values = [
        endpoint(endpoint_id=str(i).zfill(24), protocol=p, host=f"node{i}.example.com")
        for i, p in enumerate(["vless", "trojan", "vmess", "hysteria2"] * 20)
    ]
    first = select_diagnostic_targets(values, limit=16, seed="release-21")
    second = select_diagnostic_targets(list(reversed(values)), limit=16, seed="release-21")
    assert first == second
    assert len(first) == 16
    assert {x["protocol"] for x in first} == {"vless", "trojan", "vmess", "hysteria2"}
    assert len({x["endpoint_id"] for x in first}) == 16
