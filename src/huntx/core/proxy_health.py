"""Fail-closed, node-attributed HTTPS checks through an isolated proxy engine.

A TCP handshake is never accepted as proxy health. Each child has exactly one
proxy outbound, no direct fallback, and performs certificate-verified HTTPS.
Failures mean 'not publishable from this vantage now', not permanent death.
"""
from __future__ import annotations

import concurrent.futures
import http.client
import json
import logging
import math
import os
import shutil
import socket
import ssl
import subprocess
import threading
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ..formats.common.singbox import build_outbound, parse_proxy_uri

logger = logging.getLogger(__name__)
_TARGETS = (('www.gstatic.com', '/generate_204', 204),
            ('cp.cloudflare.com', '/generate_204', 204))


def _bounded(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(low, min(value, high)) if math.isfinite(value) else default


def probe_config(uri: str, port: int) -> dict[str, Any] | None:
    node = parse_proxy_uri(uri)
    if node is None:
        return None
    node.tag = 'tested-proxy'
    outbound = build_outbound(node)
    # Never attest an engine representation that silently drops URI features.
    from ..formats.common.proxy_identity import client_identity
    identity = client_identity(uri)
    if identity is not None and json.loads(identity)[1]:
        return None
    outbound['domain_resolver'] = 'local'
    return {
        'log': {'disabled': True},
        'dns': {'servers': [{'type': 'local', 'tag': 'local'}], 'final': 'local'},
        'inbounds': [{'type': 'mixed', 'listen': '127.0.0.1', 'listen_port': port}],
        'outbounds': [outbound],
        'route': {'final': 'tested-proxy', 'default_domain_resolver': 'local'},
    }


def _https_through_proxy(port: int, target: tuple[str, str, int], timeout: float) -> bool:
    host, path, status = target
    # http.client's tunnel wraps TLS using _tunnel_host as server_hostname.
    # This does not consult HTTP_PROXY/NO_PROXY and cannot retry directly.
    connection = http.client.HTTPSConnection('127.0.0.1', port, timeout=timeout,
                                             context=ssl.create_default_context())
    connection.set_tunnel(host, 443)
    try:
        connection.request('GET', path, headers={'Host': host, 'Connection': 'close'})
        response = connection.getresponse()
        return response.status == status and response.read(1) == b''
    finally:
        connection.close()


def check_proxy(uri: str, binary: str, *, timeout: float = 8.0) -> dict[str, Any]:
    started = time.monotonic()
    stop = started + timeout
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = probe_config(uri, port)
    if config is None:
        return {'ok': False, 'reason': 'unsupported'}
    with tempfile.TemporaryDirectory(prefix='huntx-probe-') as directory:
        path = Path(directory) / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        path.chmod(0o600)
        child = subprocess.Popen([binary, 'run', '-c', str(path)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Socket timeouts bound individual reads only. Killing the isolated
        # engine at the node deadline closes any stalled tunnel/socket.
        watchdog = threading.Timer(max(0.0, stop - time.monotonic()), child.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            ready = False
            while time.monotonic() < stop and child.poll() is None:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.025)
            if not ready:
                return {'ok': False, 'reason': 'engine_start_failed'}
            for index, target in enumerate(_TARGETS):
                remaining = stop - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    # Reserve time for a second independent endpoint on failure.
                    if _https_through_proxy(port, target, remaining / (len(_TARGETS) - index)):
                        return {'ok': True, 'latency_ms': round((time.monotonic() - started) * 1000),
                                'checked_at': time.time(), 'reason': 'authenticated_https'}
                except (OSError, ssl.SSLError, http.client.HTTPException):
                    continue
            return {'ok': False, 'reason': 'https_path_failed'}
        finally:
            watchdog.cancel()
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)


def _verify_engine(binary: str) -> None:
    """Distinguish broken local infrastructure from a sweep of failed nodes."""
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = {
        'log': {'disabled': True},
        'inbounds': [{'type': 'mixed', 'listen': '127.0.0.1', 'listen_port': port}],
        'outbounds': [{'type': 'direct', 'tag': 'bootstrap-only'}],
        'route': {'final': 'bootstrap-only'},
    }
    # This direct outbound only tests local engine startup: it never receives
    # a request. Per-node probes use a separate process with no direct outbound.
    with tempfile.TemporaryDirectory(prefix='huntx-engine-check-') as directory:
        path = Path(directory) / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        child = subprocess.Popen([binary, 'run', '-c', str(path)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            stop = time.monotonic() + 3
            while time.monotonic() < stop and child.poll() is None:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        return
                except OSError:
                    time.sleep(0.025)
            raise RuntimeError('Proxy verification engine could not start; publication blocked')
        finally:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)


def verified_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check each semantic identity once; return only freshly attested records."""
    from ..formats.npvt import canonical_proxy_identity

    candidates: dict[str, tuple[str, dict[str, Any]]] = {}
    for record in records:
        fields = record.get('data', record) if isinstance(record, dict) else {}
        line = fields.get('line') if isinstance(fields, dict) else None
        if isinstance(line, str):
            candidates.setdefault(canonical_proxy_identity(line), (line, fields))
    if not candidates:
        return []
    binary = shutil.which(os.getenv('HUNTX_SINGBOX_BINARY', 'sing-box'))
    if binary is None:
        raise RuntimeError('Authenticated publication checks require the sing-box engine')
    _verify_engine(binary)
    workers = int(_bounded('HUNTX_HEALTH_WORKERS', 16, 1, 32))
    timeout = _bounded('HUNTX_HEALTH_TIMEOUT', 8, 1, 30)
    budget = _bounded('HUNTX_HEALTH_BUDGET', 900, 1, 1800)
    results: dict[str, dict[str, Any]] = {}
    reasons: Counter[str] = Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_proxy, line, binary, timeout=timeout): key
                   for key, (line, _) in candidates.items()}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=budget):
                key = futures[future]
                try:
                    result = future.result()
                except Exception:
                    # Do not log exception text: engine failures may contain URIs.
                    result = {'ok': False, 'reason': 'probe_error'}
                reasons[str(result.get('reason', 'invalid_result'))] += 1
                if result.get('ok') is True:
                    checked = result.get('checked_at')
                    latency = result.get('latency_ms')
                    if (isinstance(checked, (int, float)) and not isinstance(checked, bool)
                            and math.isfinite(checked) and time.time() - 60 <= checked <= time.time()
                            and isinstance(latency, (int, float)) and not isinstance(latency, bool)
                            and math.isfinite(latency) and 0 <= latency <= timeout * 1000):
                        results[key] = result
        except TimeoutError:
            reasons['budget_exhausted'] += sum(not f.done() for f in futures)
        finally:
            for future in futures:
                future.cancel()
    accepted = []
    for key, (_, fields) in candidates.items():
        accepted_result = results.get(key)
        # Earlier successes expire too; a long sweep cannot publish stale proof.
        if accepted_result is None or time.time() - accepted_result['checked_at'] > 300:
            continue
        result = accepted_result
        accepted.append({'data': {
            **fields, 'probe_kind': 'protocol_authenticated',
            'probe_authenticated': True, 'latency_ms': result['latency_ms'],
            'probe_checked_at': result['checked_at'],
            'probe_expires_at': result['checked_at'] + 300,
        }})
    logger.info('Proxy HTTPS gate: candidates=%d accepted=%d excluded=%d reasons=%s',
                len(candidates), len(accepted), len(candidates) - len(accepted), dict(reasons))
    return accepted
