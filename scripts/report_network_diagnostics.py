#!/usr/bin/env python3
"""Bounded, opt-in DNS/TCP/TLS diagnostics on an existing proxy corpus.

This is NOT a proxy-authentication test: a healthy TLS endpoint can still reject
every proxy credential. Network tests use pinned public IPs and never send
proxy passwords or URLs to the remote endpoint. Reports omit DNS names and IPs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from huntx.core.endpoint_intelligence import describe_proxy_endpoint
from huntx.core.network_diagnostics import inspect_target, select_diagnostic_targets
from huntx.formats.common.singbox import parse_proxy_uri
from huntx.core.corpus_reader import load_active_observations

_MAX_SCAN = 50_000
_MAX_TESTED = 64
_MAX_CONCURRENCY = 8


def build_network_candidates(
    observations: Iterable[tuple[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Identify testable public endpoints from old and new active observations."""
    counts = {
        "records_seen": 0,
        "invalid_records": 0,
        "duplicate_network_endpoints": 0,
        "non_public_endpoints": 0,
    }
    by_endpoint: dict[str, dict[str, Any]] = {}
    for _source, payload in observations:
        counts["records_seen"] += 1
        if not isinstance(payload, str) or len(payload) > 32_768:
            counts["invalid_records"] += 1
            continue
        try:
            record = json.loads(payload)
        except (ValueError, TypeError):
            counts["invalid_records"] += 1
            continue
        line = record.get("line") if isinstance(record, dict) else None
        if not isinstance(line, str):
            counts["invalid_records"] += 1
            continue
        endpoint = describe_proxy_endpoint(line)
        if endpoint is None:
            counts["invalid_records"] += 1
            continue
        if endpoint["host_kind"] == "non_public_ip_literal":
            counts["non_public_endpoints"] += 1
            continue
        ident = endpoint["endpoint_id"]
        if ident in by_endpoint:
            counts["duplicate_network_endpoints"] += 1
            continue
        # In memory only: SNI is needed for certificate checking, but it is
        # never serialized. Credentials and raw URLs are discarded immediately.
        node = parse_proxy_uri(line)
        if node is None:
            counts["invalid_records"] += 1
            continue
        candidate = {
            "endpoint_id": endpoint["endpoint_id"],
            "host": endpoint["host"],
            "port": endpoint["port"],
            "host_kind": endpoint["host_kind"],
            "ip": endpoint["ip"],
            "protocol": endpoint["protocol"],
            "transport_kind": endpoint["transport_kind"],
            "transport": endpoint["transport"],
            "tls_mode": endpoint["tls_mode"],
            "tls_server_name": node.tls_server_name or None,
            "tls_source_insecure": node.tls_insecure,
        }
        by_endpoint[ident] = candidate
    return list(by_endpoint.values()), counts


async def inspect_corpus(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    seed: str,
    enabled: bool = True,
    concurrency: int = 4,
    timeout: float = 3.0,
    inspector: Callable[..., Awaitable[dict[str, Any]]] = inspect_target,
) -> dict[str, Any]:
    """Run rotating, rate-bounded observations with per-layer rollups."""
    if type(concurrency) is not int or not 1 <= concurrency <= _MAX_CONCURRENCY:
        raise ValueError("concurrency must be within 1..8")
    if type(limit) is not int or not 1 <= limit <= _MAX_TESTED:
        raise ValueError("limit must be within 1..64")
    base: dict[str, Any] = {
        "schema_version": 1,
        "scope": "dns_tcp_standard_tls_only",
        "evidence_limits": (
            "never_equivalent_to_authenticated_proxy_health;"
            "no_quic_reality_websocket_grpc_protocol_handshake;"
            "dns_ttl_cname_dnssec_not_measured"
        ),
        "observed_at": int(time.time()),
        "status": "disabled" if not enabled else "complete",
        "counts": {"candidates": len(candidates), "selected": 0, "tested": 0, "terminal": 0},
        "layers": {},
        "observations": [],
    }
    if not enabled:
        return base
    selected = select_diagnostic_targets(candidates, limit=limit, seed=seed)
    base["counts"]["selected"] = len(selected)
    semaphore = asyncio.Semaphore(concurrency)

    async def scan(target: Mapping[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                result = await inspector(target, timeout=timeout)
            except Exception:
                # Error class is intentionally fixed to prevent leaking a
                # resolver, TLS, or network exception with sensitive details.
                result = {
                    "endpoint_id": target["endpoint_id"],
                    "protocol": target["protocol"],
                    "dns": {"status": "probe_infrastructure_error"},
                    "tcp": {"status": "not_attempted"},
                    "tls": {"status": "not_attempted"},
                    "transport_protocol": {"status": "unverified"},
                    "proxy_protocol": {"status": "unverified"},
                    "disposition": "evidence_unavailable",
                    "terminal": False,
                    "next_action": "retry_from_independent_vantage",
                }
            # Enforce a privacy allowlist even if a downstream inspector has
            # accidentally introduced raw hostname or credential fields.
            safe: dict[str, Any] = {
                key: result[key] for key in (
                    "endpoint_id", "protocol", "checked_at",
                    "evidence_scope", "disposition", "terminal", "next_action"
                ) if key in result
            }
            for name in ("dns", "tcp", "tls", "proxy_protocol", "transport_protocol"):
                data = result.get(name, {})
                clean = {
                    k: data[k] for k in (
                        "status", "ipv4_count", "ipv6_count", "version",
                        "alpn", "verified_hostname",
                    ) if isinstance(data, dict) and k in data
                    and isinstance(data[k], (int, str, bool))
                }
                safe[name] = clean or {"status": "unknown"}
            # Do not allow an inspector to signal permanent death. Only the
            # separate explicit policy ledger can terminalize identities.
            safe["terminal"] = False
            return safe

    results = await asyncio.gather(*(scan(target) for target in selected))
    base["observations"] = results
    base["counts"]["tested"] = len(results)
    base["counts"]["infrastructure_errors"] = sum(
        item["disposition"] == "evidence_unavailable" for item in results
    )
    if base["counts"]["infrastructure_errors"]:
        base["status"] = "partial"
    for layer in ("dns", "tcp", "tls", "transport_protocol", "proxy_protocol"):
        outcomes = Counter(str(item[layer].get("status", "unknown")) for item in results)
        base["layers"][layer] = dict(sorted(outcomes.items()))
    return base


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    records = load_active_observations(args.db, limit=args.max_records)
    if records is None:
        return {
            "schema_version": 1, "scope": "dns_tcp_standard_tls_only",
            "status": "evidence_unavailable", "observed_at": int(time.time()),
            "counts": {"records_seen": 0, "tested": 0}, "layers": {},
            "observations": [], "evidence_limits": "no_runtime_database",
        }
    rows, truncated = records
    candidates, inventory_counts = build_network_candidates(rows)
    report = await inspect_corpus(
        candidates, limit=args.max_endpoints, seed=args.seed,
        enabled=args.enable_network, concurrency=args.concurrency,
        timeout=args.timeout,
    )
    report["counts"].update(inventory_counts)
    report["counts"]["corpus_scan_truncated"] = truncated
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-records", type=int, default=50_000)
    parser.add_argument("--max-endpoints", type=int, default=24)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--enable-network", action="store_true")
    parser.add_argument("--seed", default=os.environ.get("GITHUB_RUN_ID", "manual"))
    args = parser.parse_args()
    if not 1 <= args.max_records <= _MAX_SCAN:
        parser.error("max-records must be within 1..50000")
    if not 1 <= args.max_endpoints <= _MAX_TESTED:
        parser.error("max-endpoints must be within 1..64")
    if not 1 <= args.concurrency <= _MAX_CONCURRENCY:
        parser.error("concurrency must be within 1..8")
    if not 0 < args.timeout <= 5.0:
        parser.error("timeout must be within (0, 5]")
    snapshot = asyncio.run(_run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        "network-diagnostics: status=%s scanned=%d sampled=%d infrastructure_errors=%d"
        % (
            snapshot["status"], snapshot["counts"].get("records_seen", 0),
            snapshot["counts"].get("tested", 0),
            snapshot["counts"].get("infrastructure_errors", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
