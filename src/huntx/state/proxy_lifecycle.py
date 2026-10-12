"""Persistent, source-independent proxy lifecycle and authenticated probe ledger.

Passive rediscovery can update last-seen timestamps, but can never clear a
terminal verdict. TCP connects and feed parse checks do not count as proxy
authentication, and cannot promote a configuration to ACTIVE.
"""
from __future__ import annotations

import math
import sqlite3
import time
from typing import Iterable, Any

_TERMINAL = frozenset({"dead", "revoked", "archived"})
_PROXY_TYPES = frozenset({"npvt", "npvtsub"})


def _identity(record_type: str, unique_hash: str) -> tuple[str, str]:
    if record_type not in _PROXY_TYPES:
        raise ValueError("only proxy records carry proxy lifecycle status")
    if not isinstance(unique_hash, str) or len(unique_hash) != 64 or any(
        char not in "0123456789abcdef" for char in unique_hash
    ):
        raise ValueError("proxy identity must be a canonical sha256 digest")
    return record_type, unique_hash


def observe_record_identities(
    *, c: sqlite3.Connection, identities: Iterable[tuple[str, str]],
    now: int | None = None,
) -> int:
    """Backfill discovery timestamps without weakening existing verdicts.

    This runs inside the ingestion transaction. Invalid legacy test records
    and non-proxy files have no lifecycle row, preserving old API behavior.
    """
    clock = int(time.time()) if now is None else int(now)
    valid = sorted({
        (record_type, unique_hash) for record_type, unique_hash in identities
        if record_type in _PROXY_TYPES and isinstance(unique_hash, str)
        and len(unique_hash) == 64 and all(ch in "0123456789abcdef" for ch in unique_hash)
    })
    if valid:
        c.executemany(
            """
            INSERT INTO proxy_lifecycle(
                unique_hash, record_type, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(unique_hash, record_type) DO UPDATE SET
                last_seen_at = MAX(proxy_lifecycle.last_seen_at, excluded.last_seen_at)
            """,
            [(digest, kind, clock, clock) for kind, digest in valid],
        )
    return len(valid)


def record_authenticated_probe(
    db: Any, *, unique_hash: str, record_type: str,
    probe_id: str, vantage_id: str, success: bool,
    latency_ms: float | None = None, checked_at: int | None = None,
    evidence_kind: str = "protocol_authenticated",
) -> bool:
    """Record exactly-once protocol evidence; returns False for duplicate IDs.

    Terminal proxy hashes stay terminal regardless of repeated source
    appearances or even later claimed success. A legitimate changed config
    receives a different canonical identity and can be evaluated afresh.
    """
    kind, digest = _identity(record_type, unique_hash)
    if evidence_kind != "protocol_authenticated" or type(success) is not bool:
        raise ValueError("only authenticated proxy protocol probes may change lifecycle")
    if not isinstance(probe_id, str) or not 1 <= len(probe_id) <= 128:
        raise ValueError("a bounded unique probe receipt is required")
    if not isinstance(vantage_id, str) or not 1 <= len(vantage_id) <= 64:
        raise ValueError("vantage provenance is required")
    if latency_ms is not None and (
        isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float))
        or not math.isfinite(latency_ms) or latency_ms < 0
    ):
        raise ValueError("latency must be finite and nonnegative")
    now = int(time.time())
    tick = now if checked_at is None else int(checked_at)
    if tick <= 0 or tick > now + 300:
        raise ValueError("probe timestamp is not valid")
    with db.connect() as c:
        observe_record_identities(c=c, identities=[(kind, digest)], now=tick)
        existing = c.execute(
            "SELECT lifecycle_status FROM proxy_lifecycle WHERE unique_hash = ? "
            "AND record_type = ?", (digest, kind),
        ).fetchone()
        if existing is None:
            raise RuntimeError("missing lifecycle identity after insertion")
        if existing["lifecycle_status"] in _TERMINAL:
            raise ValueError("terminal proxy identities cannot be revived")
        prior = c.execute(
            "SELECT unique_hash, record_type FROM proxy_probe_history WHERE probe_id = ?",
            (probe_id,),
        ).fetchone()
        if prior is not None:
            if prior["unique_hash"] != digest or prior["record_type"] != kind:
                raise ValueError("probe receipt reused for a different identity")
            return False
        # A late result from an older probe must not override newer failures
        # or make stale authenticated success appear current. Same-second
        # observations remain valid; probe receipts enforce idempotence.
        previous_probe_at = c.execute(
            "SELECT last_probe_at FROM proxy_lifecycle WHERE unique_hash = ? "
            "AND record_type = ?", (digest, kind),
        ).fetchone()["last_probe_at"]
        if previous_probe_at is not None and tick < int(previous_probe_at):
            raise ValueError("out-of-order authenticated probe cannot overwrite newer evidence")
        inserted = c.execute(
            """
            INSERT INTO proxy_probe_history(
                probe_id, unique_hash, record_type, vantage_id, checked_at,
                success, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(probe_id) DO NOTHING
            """,
            (probe_id, digest, kind, vantage_id, tick, int(success), latency_ms),
        )
        if inserted.rowcount == 0:
            owner = c.execute(
                "SELECT unique_hash, record_type FROM proxy_probe_history WHERE probe_id = ?",
                (probe_id,),
            ).fetchone()
            if owner is None or owner["unique_hash"] != digest or owner["record_type"] != kind:
                raise ValueError("probe receipt reused for a different identity")
            return False
        if success:
            c.execute(
                """
                UPDATE proxy_lifecycle SET lifecycle_status = 'active',
                    last_success_at = ?, authenticated_successes = authenticated_successes + 1,
                    consecutive_failures = 0, last_probe_at = ?,
                    last_probe_result = 'pass', last_reason_code = ''
                WHERE unique_hash = ? AND record_type = ?
                """,
                (tick, tick, digest, kind),
            )
        else:
            c.execute(
                """
                UPDATE proxy_lifecycle SET
                    lifecycle_status = CASE WHEN consecutive_failures >= 2
                        THEN 'suspect' ELSE 'degraded' END,
                    authenticated_failures = authenticated_failures + 1,
                    consecutive_failures = consecutive_failures + 1,
                    last_probe_at = ?, last_probe_result = 'fail',
                    last_reason_code = 'authenticated_protocol_failure'
                WHERE unique_hash = ? AND record_type = ?
                """,
                (tick, digest, kind),
            )
    return True


def terminalize_proxy(
    db: Any, *, unique_hash: str, record_type: str,
    reason_code: str, status: str = "dead",
) -> None:
    """Explicit terminal policy decision. No passive/eventual resurrection."""
    kind, digest = _identity(record_type, unique_hash)
    if status not in _TERMINAL:
        raise ValueError("expected a terminal lifecycle status")
    if not isinstance(reason_code, str) or not 1 <= len(reason_code) <= 100 or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789_:-" for char in reason_code
    ):
        raise ValueError("provide a bounded machine-readable reason code")
    with db.connect() as c:
        observe_record_identities(c=c, identities=[(kind, digest)])
        c.execute(
            """
            UPDATE proxy_lifecycle SET lifecycle_status = ?, last_reason_code = ?
            WHERE unique_hash = ? AND record_type = ?
              AND lifecycle_status NOT IN ('dead', 'revoked', 'archived')
            """,
            (status, reason_code, digest, kind),
        )


def describe_proxy(db: Any, *, unique_hash: str, record_type: str) -> dict[str, Any] | None:
    kind, digest = _identity(record_type, unique_hash)
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?",
            (digest, kind),
        ).fetchone()
    return dict(row) if row else None
