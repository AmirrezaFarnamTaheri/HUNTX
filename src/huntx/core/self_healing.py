import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_BACKOFF_SCHEDULE = [300, 900, 3600, 21600]  # 5m, 15m, 1h, 6h in seconds


class SelfHealingDaemon:
    """
    Autonomous background health poller and dead node auto-purger.
    Implements exponential backoff retry scheduling and 48h stale node purging.
    """

    def __init__(self, db_path: str = ":memory:", backoff_schedule: Optional[List[int]] = None):
        self.db_path = db_path
        self.backoff_schedule = backoff_schedule or DEFAULT_BACKOFF_SCHEDULE
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._conn is None:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            return self._conn
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection and explicitly close file-backed connections."""
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
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS degraded_proxies (
                    unique_hash TEXT PRIMARY KEY,
                    raw_uri TEXT NOT NULL,
                    fail_count INTEGER DEFAULT 1,
                    first_failed_at REAL NOT NULL,
                    next_check_at REAL NOT NULL,
                    status TEXT DEFAULT 'degraded'
                )
                """
            )
            conn.commit()

    def record_failure(self, unique_hash: str, raw_uri: str, current_time: Optional[float] = None) -> Tuple[int, float]:
        """
        Records a proxy failure and calculates next retry timestamp based on exponential backoff.
        """
        now = time.time() if current_time is None else current_time
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fail_count, first_failed_at FROM degraded_proxies WHERE unique_hash = ?",
                (unique_hash,),
            )
            row = cursor.fetchone()

            if row:
                fail_count = row[0] + 1
                first_failed_at = row[1]
            else:
                fail_count = 1
                first_failed_at = now

            backoff_idx = min(fail_count - 1, len(self.backoff_schedule) - 1)
            interval = self.backoff_schedule[backoff_idx]
            next_check = now + interval

            cursor.execute(
                """
                INSERT INTO degraded_proxies (unique_hash, raw_uri, fail_count, first_failed_at, next_check_at, status)
                VALUES (?, ?, ?, ?, ?, 'degraded')
                ON CONFLICT(unique_hash) DO UPDATE SET
                    fail_count = excluded.fail_count,
                    next_check_at = excluded.next_check_at,
                    status = 'degraded'
                """,
                (unique_hash, raw_uri, fail_count, first_failed_at, next_check),
            )
            conn.commit()
        return fail_count, next_check

    def reinstate_proxy(self, unique_hash: str) -> bool:
        """
        Reinstates a recovered proxy to active status by removing it from degraded state.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
            conn.commit()
            deleted = cursor.rowcount
        return deleted > 0

    def get_due_for_retest(self, current_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Returns list of degraded proxies due for re-testing.
        """
        now = time.time() if current_time is None else current_time
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT unique_hash, raw_uri, fail_count, first_failed_at, next_check_at
                FROM degraded_proxies
                WHERE next_check_at <= ? AND status = 'degraded'
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

    def purge_stale_proxies(self, max_age_hours: int = 48, current_time: Optional[float] = None) -> int:
        """
        Purges degraded proxies that have remained unreachable for > max_age_hours (default 48h).
        """
        now = time.time() if current_time is None else current_time
        cutoff = now - (max_age_hours * 3600)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM degraded_proxies WHERE first_failed_at <= ?", (cutoff,))
            conn.commit()
            deleted = cursor.rowcount
        return deleted

    def run_poller_cycle(self, current_time: Optional[float] = None) -> Dict[str, int]:
        """
        H-N Phase 3 plan contract: run one poller cycle.
        1. Purge proxies stale > 48h.
        2. Collect all proxies due for re-test.
        3. Advance their backoff (re-record failure, bump fail_count).
        Returns: {"retested": int, "reinstated": int, "purged": int}
        """
        now = time.time() if current_time is None else current_time
        purged = self.purge_stale_proxies(max_age_hours=48, current_time=now)
        due = self.get_due_for_retest(current_time=now)
        retested = 0
        for proxy in due:
            self.record_failure(proxy["unique_hash"], proxy["raw_uri"], current_time=now)
            retested += 1
        return {"retested": retested, "reinstated": 0, "purged": purged}
