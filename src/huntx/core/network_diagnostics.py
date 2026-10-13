"""Safe, bounded, layer-separated network observations for public proxy endpoints.

DNS resolution, TCP connect, standard TLS verification and full proxy protocol
authentication are different tests. This module never sends proxy credentials,
HTTP/WebSocket upgrade requests or QUIC/REALITY protocol handshakes. Failures
are hints for recovery, never sufficient evidence for permanent revocation.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import math
import re
import socket
import ssl
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

_RESOLVER = Callable[..., Awaitable[list[tuple[Any, ...]]]]
_CONNECTOR = Callable[..., Awaitable[tuple[Any, Any]]]
_MAX_TIMEOUT = 5.0
_PORT_MAX = 65535
_PROTOCOL = re.compile(r"^[a-z0-9_+-]{1,24}$")
_VALID_ID = re.compile(r"^[a-z0-9]{12,64}$")
_SOFT_ACTIONS = {
    "dns_timeout": "retry_dns_from_independent_resolvers",
    "dns_no_data_or_name_error": "retry_dns_from_independent_resolvers",
    "dns_temporary_failure": "retry_dns_from_independent_resolvers",
    "dns_no_public_addresses": "inspect_dns_and_public_route",
    "tcp_refused": "retry_tcp_from_independent_vantage",
    "tcp_timeout": "retry_tcp_from_independent_vantage",
    "tls_certificate_verification_failed": "inspect_sni_certificate_chain_and_clock",
    "tls_handshake_error": "inspect_sni_tls_version_and_alpn",
    "transport_unsupported": "test_with_native_transport_client",
    "reality_requires_native_probe": "test_with_native_reality_client",
    "protocol_auth_failed": "refresh_credentials_and_retest",
    "source_unavailable": "retry_source_and_check_alternates",
    "expired_evidence": "retest_with_fresh_evidence",
    "ip_family_mismatch": "retry_other_public_address_family",
    "cdn_fronting_unknown": "inspect_sni_cdn_origin_and_path",
    "tls_insecure_configured": "review_certificate_verification_configuration",
    "structurally_invalid_configuration": "exclude_invalid_config_and_attempt_repair",
}


def classify_network_issue(code: str, *, authoritative_revocation: bool = False) -> dict[str, Any]:
    """Conservative disposition: no network test proves permanent death."""
    if code == "verified_credential_revocation" and authoritative_revocation is True:
        return {
            "disposition": "terminal_policy_review",
            "terminal": True,
            "next_action": "record_explicit_revocation_with_receipt",
        }
    if code == "structurally_invalid_configuration":
        return {
            "disposition": "non_publishable_repair_candidate",
            "terminal": False,
            "next_action": _SOFT_ACTIONS[code],
        }
    return {
        "disposition": "recoverable",
        "terminal": False,
        "next_action": _SOFT_ACTIONS.get(code, "inspect_observation_and_retest"),
    }


def _clean_public_address(value: Any, *, expected_family: int | None = None) -> tuple[str, int] | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if not address.is_global:
        return None
    family = socket.AF_INET if address.version == 4 else socket.AF_INET6
    if expected_family is not None and family != expected_family:
        return None
    return str(address), family


def _result_stub(target: Mapping[str, Any], checked_at: int) -> dict[str, Any]:
    endpoint_id = target.get("endpoint_id")
    if not isinstance(endpoint_id, str) or not _VALID_ID.fullmatch(endpoint_id):
        endpoint_id = "invalid"
    protocol = target.get("protocol")
    if not isinstance(protocol, str) or not _PROTOCOL.fullmatch(protocol):
        protocol = "unknown"
    return {
        "schema_version": 1,
        "endpoint_id": endpoint_id,
        "protocol": protocol,
        "checked_at": checked_at,
        "evidence_scope": "dns_tcp_tls_only_not_authenticated_proxy",
        "dns": {"status": "not_attempted", "ipv4_count": 0, "ipv6_count": 0},
        "tcp": {"status": "not_attempted"},
        "tls": {"status": "not_attempted"},
        "transport_protocol": {"status": "unverified"},
        "proxy_protocol": {"status": "unverified"},
        "disposition": "recoverable",
        "terminal": False,
        "next_action": "obtain_protocol_authenticated_probe",
    }


def _safe_host(value: Any) -> bool:
    if not isinstance(value, str) or not 0 < len(value) <= 253:
        return False
    try:
        ascii_host = value.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return (
        len(ascii_host) <= 253
        and "." in ascii_host
        and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in ascii_host.split("."))
        and not ascii_host.lower().endswith((".local", ".internal", ".invalid", ".test", ".localhost"))
    )


def _safe_method_outcome(record: dict[str, Any], code: str) -> None:
    classified = classify_network_issue(code)
    record.update(classified)


async def inspect_target(
    target: Mapping[str, Any],
    *,
    resolver: _RESOLVER | None = None,
    connector: _CONNECTOR | None = None,
    timeout: float = 3.0,
    observed_at: int | None = None,
) -> dict[str, Any]:
    """Probe only a validated public address, pinned after resolution.

    No password, UUID, SNI, raw hostname, IP or upstream exception is emitted.
    A standard TLS certificate may be tested; REALITY/QUIC/WS/gRPC must be
    checked separately with protocol-specific, authenticated probes.
    """
    checked_at = int(time.time()) if observed_at is None else int(observed_at)
    record = _result_stub(target, checked_at)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout):
        raise ValueError("timeout must be a finite number")
    if not 0 < timeout <= _MAX_TIMEOUT:
        raise ValueError("timeout must be between zero and five seconds")
    host = target.get("host")
    port = target.get("port")
    if (
        not isinstance(host, str) or type(port) is not int
        or not 1 <= port <= _PORT_MAX
    ):
        record["dns"]["status"] = "invalid_target"
        _safe_method_outcome(record, "structurally_invalid_configuration")
        return record

    ip_value = _clean_public_address(host)
    dns_mode = target.get("host_kind")
    selected: list[tuple[str, int]] = []
    if ip_value is not None:
        selected = [ip_value]
        record["dns"]["status"] = "public_ip_literal"
    else:
        try:
            parsed_ip = ipaddress.ip_address(host)
        except ValueError:
            parsed_ip = None
        if parsed_ip is not None:
            record["dns"]["status"] = "non_public_literal"
            _safe_method_outcome(record, "dns_no_public_addresses")
            return record
        if dns_mode != "dns_name" or not _safe_host(host):
            record["dns"]["status"] = "invalid_target"
            _safe_method_outcome(record, "structurally_invalid_configuration")
            return record
        lookup = resolver or asyncio.get_running_loop().getaddrinfo
        try:
            infos = await asyncio.wait_for(
                lookup(host, port, type=socket.SOCK_STREAM), timeout=timeout
            )
        except (TimeoutError, asyncio.TimeoutError):
            record["dns"]["status"] = "timeout"
            _safe_method_outcome(record, "dns_timeout")
            return record
        except socket.gaierror as exc:
            if exc.errno == socket.EAI_AGAIN:
                record["dns"]["status"] = "temporary_failure"
                _safe_method_outcome(record, "dns_temporary_failure")
            else:
                # getaddrinfo does not distinguish NXDOMAIN from NODATA.
                record["dns"]["status"] = "no_data_or_name_error"
                _safe_method_outcome(record, "dns_no_data_or_name_error")
            return record
        except (OSError, ValueError):
            record["dns"]["status"] = "resolver_error"
            _safe_method_outcome(record, "dns_timeout")
            return record
        addresses: set[tuple[str, int]] = set()
        for item in infos[:128]:
            if not isinstance(item, tuple) or len(item) < 5:
                continue
            family, socktype, _protocol, _canonical, endpoint = item[:5]
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            if socktype != socket.SOCK_STREAM or not isinstance(endpoint, tuple) or not endpoint:
                continue
            public = _clean_public_address(endpoint[0], expected_family=family)
            if public is not None:
                addresses.add(public)
        selected = sorted(addresses, key=lambda item: (item[1] != socket.AF_INET, item[0]))
        if not selected:
            record["dns"]["status"] = "no_public_addresses"
            _safe_method_outcome(record, "dns_no_public_addresses")
            return record
        record["dns"]["status"] = "resolved_public"

    record["dns"]["ipv4_count"] = sum(f == socket.AF_INET for _, f in selected)
    record["dns"]["ipv6_count"] = sum(f == socket.AF_INET6 for _, f in selected)

    transport = target.get("transport_kind")
    tls_mode = target.get("tls_mode")
    if transport == "udp":
        record["tcp"]["status"] = "not_applicable_udp"
        record["tls"]["status"] = "not_applicable_udp"
        record["next_action"] = "test_with_native_udp_proxy_client"
        return record

    ssl_context: ssl.SSLContext | None = None
    sni: str | None = None
    if tls_mode == "tls":
        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        # Never bypass CA chain or hostname verification, even if the source
        # requests insecure TLS. Such configurations merit separate review.
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        sni_value = target.get("tls_server_name") or host
        if _safe_host(sni_value) or _clean_public_address(sni_value):
            sni = str(sni_value)
        else:
            record["tls"]["status"] = "invalid_sni"
            _safe_method_outcome(record, "tls_handshake_error")
            return record
        if target.get("transport") == "grpc":
            ssl_context.set_alpn_protocols(["h2", "http/1.1"])
        else:
            ssl_context.set_alpn_protocols(["http/1.1", "h2"])
    elif tls_mode == "reality":
        record["tls"]["status"] = "requires_protocol_specific_probe"
    elif tls_mode == "none":
        record["tls"]["status"] = "not_configured"
    else:
        record["tls"]["status"] = "unsupported_configuration"
        _safe_method_outcome(record, "transport_unsupported")
        return record

    dial = connector or asyncio.open_connection
    dest, family = selected[0]
    try:
        options: dict[str, Any] = {"family": family}
        if ssl_context is not None:
            options.update(ssl=ssl_context, server_hostname=sni)
        _reader, writer = await asyncio.wait_for(
            dial(dest, port, **options), timeout=timeout
        )
    except ssl.SSLCertVerificationError:
        record["tcp"]["status"] = "indeterminate_tls_connect"
        record["tls"]["status"] = "certificate_verification_failed"
        _safe_method_outcome(record, "tls_certificate_verification_failed")
        return record
    except ssl.SSLError:
        record["tcp"]["status"] = "indeterminate_tls_connect"
        record["tls"]["status"] = "handshake_failed"
        _safe_method_outcome(record, "tls_handshake_error")
        return record
    except (TimeoutError, asyncio.TimeoutError):
        record["tcp"]["status"] = "timeout"
        _safe_method_outcome(record, "tcp_timeout")
        return record
    except (OSError, ConnectionError):
        record["tcp"]["status"] = "connect_failed"
        _safe_method_outcome(record, "tcp_refused")
        return record
    record["tcp"]["status"] = "connected"
    try:
        if ssl_context is not None:
            tls = writer.get_extra_info("ssl_object")
            if tls is None:
                record["tls"]["status"] = "no_tls_receipt"
            else:
                version = tls.version()
                alpn = tls.selected_alpn_protocol()
                record["tls"] = {
                    "status": "verified_handshake",
                    "version": version if version in {"TLSv1.2", "TLSv1.3"} else "other",
                    "alpn": alpn if alpn in {"http/1.1", "h2"} else "unknown",
                    "verified_hostname": True,
                }
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=min(1.0, timeout))
        except (OSError, TimeoutError, asyncio.TimeoutError):
            pass
    return record


def select_diagnostic_targets(
    candidates: Sequence[Mapping[str, Any]], *, limit: int, seed: str
) -> list[dict[str, Any]]:
    """Rotate bounded coverage across protocols without source-order bias."""
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError("target limit must be 1..256")
    buckets: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    unique: set[str] = set()
    for row in candidates:
        ident = row.get("endpoint_id")
        if not isinstance(ident, str) or ident in unique:
            continue
        unique.add(ident)
        protocol = row.get("protocol")
        if not isinstance(protocol, str) or not _PROTOCOL.fullmatch(protocol):
            protocol = "unknown"
        key = hashlib.sha256(f"{seed}|{ident}".encode("utf-8")).hexdigest()
        buckets[protocol].append((key, dict(row)))
    for rows in buckets.values():
        rows.sort(key=lambda pair: (pair[0], str(pair[1].get("endpoint_id"))))
    chosen: list[dict[str, Any]] = []
    protocols = sorted(buckets)
    while len(chosen) < limit and protocols:
        remaining: list[str] = []
        for protocol in protocols:
            if len(chosen) == limit:
                break
            if buckets[protocol]:
                chosen.append(buckets[protocol].pop(0)[1])
            if buckets[protocol]:
                remaining.append(protocol)
        protocols = remaining
    return chosen
