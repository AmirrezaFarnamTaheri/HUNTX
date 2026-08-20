from __future__ import annotations

import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

DEFAULT_BACKOFF_SCHEDULE = (300, 900, 3600, 21600)  # 5m, 15m, 1h, 6h in seconds


def _validate_backoff_schedule(schedule: Optional[Sequence[int]]) -> tuple[int, ...]:
    values = DEFAULT_BACKOFF_SCHEDULE if schedule is None else tuple(schedule)
    if not values:
        raise ValueError("backoff_schedule must contain at least one interval")
    normalized: list[int] = []
    for raw in values:
        if isinstance(raw, bool):
            raise ValueError("backoff_schedule intervals must be positive integers")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("backoff_schedule intervals must be positive integers") from exc
        if value <= 0 or value != raw:
            raise ValueError("backoff_schedule intervals must be positive integers")
        normalized.append(value)
    return tuple(normalized)


def _finite_time(value: Optional[float]) -> float:
    now = time.time() if value is None else float(value)
    if not math.isfinite(now):
        raise ValueError("current_time must be finite")
    return now


class SelfHealingDaemon:
    """Durable degraded-node retry scheduler and stale-entry purger.

    The helper is deliberately passive: one poller cycle advances retry state;
    the caller owns the actual network probe and may reinstate a recovered node.
    SQLite access is serialized per instance so the shared in-memory connection
    remains safe when the public helper is used from concurrent worker threads.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        backoff_schedule: Optional[Sequence[int]] = None,
    ) -> None:
        self.db_path = db_path
        self.backoff_schedule = _validate_backoff_schedule(backoff_schedule)
        self._conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._conn is None:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            return self._conn
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield one serialized connection and close file-backed handles."""
        with self._db_lock:
            if self.db_path == ":memory:":
                yield self._get_conn()
                return

            conn = self._get_conn()
            try:
                yield conn
            finally:
                conn.close()

    def close(self) -> None:
        """Close the persistent in-memory connection, if one is open."""
        with self._db_lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "SelfHealingDaemon":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS degraded_proxies (
                    unique_hash TEXT PRIMARY KEY,
                    raw_uri TEXT NOT NULL,
                    fail_count INTEGER NOT NULL DEFAULT 1 CHECK(fail_count >= 1),
                    first_failed_at REAL NOT NULL,
                    next_check_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'degraded'
                        CHECK(status = 'degraded')
                )
                """
            )
            conn.commit()

    def record_failure(
        self,
        unique_hash: str,
        raw_uri: str,
        current_time: Optional[float] = None,
    ) -> Tuple[int, float]:
        """Record a failure and schedule the next bounded retry interval."""
        if not isinstance(unique_hash, str) or not unique_hash.strip():
            raise ValueError("unique_hash must be a non-empty string")
        if not isinstance(raw_uri, str) or not raw_uri.strip():
            raise ValueError("raw_uri must be a non-empty string")
        now = _finite_time(current_time)

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fail_count, first_failed_at FROM degraded_proxies WHERE unique_hash = ?",
                (unique_hash,),
            )
            row = cursor.fetchone()

            if row:
                fail_count = int(row[0]) + 1
                first_failed_at = float(row[1])
            else:
                fail_count = 1
                first_failed_at = now

            interval = self.backoff_schedule[
                min(fail_count - 1, len(self.backoff_schedule) - 1)
            ]
            next_check = now + interval

            cursor.execute(
                """
                INSERT INTO degraded_proxies
                    (unique_hash, raw_uri, fail_count, first_failed_at, next_check_at, status)
                VALUES (?, ?, ?, ?, ?, 'degraded')
                ON CONFLICT(unique_hash) DO UPDATE SET
                    raw_uri = excluded.raw_uri,
                    fail_count = excluded.fail_count,
                    first_failed_at = excluded.first_failed_at,
                    next_check_at = excluded.next_check_at,
                    status = 'degraded'
                """,
                (unique_hash, raw_uri, fail_count, first_failed_at, next_check),
            )
            conn.commit()
        return fail_count, next_check

    def reinstate_proxy(self, unique_hash: str) -> bool:
        """Remove a recovered proxy from degraded state."""
        if not isinstance(unique_hash, str) or not unique_hash.strip():
            return False
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
            conn.commit()
            deleted = cursor.rowcount
        return deleted > 0

    def get_due_for_retest(
        self,
        current_time: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Return degraded proxies whose next retry time has arrived."""
        now = _finite_time(current_time)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT unique_hash, raw_uri, fail_count, first_failed_at, next_check_at
                FROM degraded_proxies
                WHERE next_check_at <= ? AND status = 'degraded'
                ORDER BY next_check_at ASC, unique_hash ASC
                """,
                (now,),
            )
            rows = cursor.fetchall()
        return [
            {
                "unique_hash": row[0],
                "raw_uri": row[1],
                "fail_count": row[2],
                "first_failed_at": row[3],
                "next_check_at": row[4],
            }
            for row in rows
        ]

    def purge_stale_proxies(
        self,
        max_age_hours: float = 48,
        current_time: Optional[float] = None,
    ) -> int:
        """Purge degraded proxies older than a positive finite age threshold.

        A non-positive age is a no-op rather than an accidental "purge all"
        switch. This mirrors the defensive contract used by the Go healing
        helper and makes operator mistakes fail safe.
        """
        try:
            age_hours = float(max_age_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_age_hours must be numeric") from exc
        if not math.isfinite(age_hours):
            raise ValueError("max_age_hours must be finite")
        if age_hours <= 0:
            return 0

        now = _finite_time(current_time)
        cutoff = now - (age_hours * 3600)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM degraded_proxies WHERE first_failed_at <= ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cursor.rowcount
        return deleted

    def run_poller_cycle(self, current_time: Optional[float] = None) -> Dict[str, int]:
        """Advance one deterministic retry/purge scheduling cycle.

        This method does not claim a network retest succeeded. It advances due
        entries to their next retry slot and reports how many were scheduled.
        Callers that actually probe a node should call :meth:`reinstate_proxy`
        on success.
        """
        now = _finite_time(current_time)
        purged = self.purge_stale_proxies(max_age_hours=48, current_time=now)
        due = self.get_due_for_retest(current_time=now)
        retested = 0
        for proxy in due:
            self.record_failure(
                proxy["unique_hash"],
                proxy["raw_uri"],
                current_time=now,
            )
            retested += 1
        return {"retested": retested, "reinstated": 0, "purged": purged}
