"""Bounded publish-vantage DNS/TCP evidence for honest subscription names.

This is intentionally NOT a proxy protocol or bandwidth test. Public numeric
DNS answers are pinned before connecting, preventing private-address probing
and DNS rebinding; credentials are never sent to any endpoint.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import math
import socket
import time
from typing import Iterable

from ..formats.common.singbox import parse_proxy_uri
from .latency_benchmarker import _public_addresses


_TCP_TIMEOUT = 1.5
_MAX_TARGETS = 2500
_WORKERS = 24
_OBSERVATION_TTL = 900
_UDP_PROTOCOLS = frozenset({'hysteria', 'hysteria2', 'hy2', 'tuic', 'wireguard', 'juicity', 'dnstt'})


def _endpoint(uri: str) -> tuple[str, int] | None:
    try:
        node = parse_proxy_uri(uri)
    except (TypeError, ValueError, UnicodeError, OverflowError):
        return None
    if (node is None or node.type in _UDP_PROTOCOLS or node.naive_quic
            or not node.server or type(node.port) is not int
            or not 1 <= node.port <= 65535):
        return None
    return node.server.strip().lower(), node.port


def _measure(target: tuple[str, int]) -> tuple[tuple[str, int], dict]:
    host, port = target
    now = time.time()
    try:
        literal = ipaddress.ip_address(host)
        is_dns = False
        if not literal.is_global:
            return target, {}
    except ValueError:
        is_dns = True
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError, UnicodeError):
        return target, (
            {'dns_status': 'failed', 'dns_checked_at': now,
             'dns_expires_at': now + _OBSERVATION_TTL} if is_dns else {}
        )
    public = _public_addresses(answers)
    if not public:
        return target, {}
    evidence: dict = (
        {'dns_status': 'resolved', 'dns_checked_at': now,
         'dns_expires_at': now + _OBSERVATION_TTL} if is_dns else {}
    )
    # A DNS answer is a location input, not proof of proxy connectivity.
    # Use only already filtered public addresses and retain it inside the build.
    evidence['geoip_address'] = public[0][1]
    started = time.monotonic()
    for family, address in public[:2]:
        remaining = _TCP_TIMEOUT - (time.monotonic() - started)
        if remaining <= 0:
            break
        try:
            with socket.socket(family, socket.SOCK_STREAM) as conn:
                conn.settimeout(remaining)
                destination = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
                conn.connect(destination)
            elapsed = (time.monotonic() - started) * 1000
            if math.isfinite(elapsed):
                evidence.update({
                    'probe_kind': 'tcp_connect', 'probe_authenticated': False,
                    'latency_ms': round(elapsed, 1),
                    'probe_checked_at': now, 'probe_expires_at': now + _OBSERVATION_TTL,
                })
            break
        except (OSError, ValueError, TypeError):
            continue
    return target, evidence


def probe_remark_evidence(uris: Iterable[str]) -> dict[str, dict]:
    """Return optional fresh observations keyed by unchanged URI.

    Only a bounded number of unique public TCP targets is attempted. All
    other links remain fully included in the feed, with honest missing stats.
    """
    by_target: dict[tuple[str, int], list[str]] = {}
    for uri in uris:
        if not isinstance(uri, str):
            continue
        target = _endpoint(uri)
        if target is not None and (target in by_target or len(by_target) < _MAX_TARGETS):
            by_target.setdefault(target, []).append(uri)
    if not by_target:
        return {}
    measurements: dict[tuple[str, int], dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        for target, fields in executor.map(_measure, by_target):
            if fields:
                measurements[target] = fields
    return {
        uri: dict(measurements[target])
        for target, originals in by_target.items()
        for uri in originals if target in measurements
    }
