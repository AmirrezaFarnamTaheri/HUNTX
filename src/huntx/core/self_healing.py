import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_BACKOFF_SCHEDULE = [300, 900, 3600, 21600]


class SelfHealingDaemon:
    """Autonomous background health poller and dead node auto-purger."""

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
        conn = self._get_conn()
        try:
            yield conn
        finally:
            if conn is not self._conn:
                conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS degraded_proxies (
                    unique_hash TEXT PRIMARY KEY,
                    raw_uri TEXT NOT NULL,
                    fail_count INTEGER DEFAULT 1,
                    first_failed_at REAL NOT NULL,
                    next_check_at REAL NOT NULL,
                    status TEXT DEFAULT 'degraded'
                )
            """)
            conn.commit()

    def record_failure(self, unique_hash: str, raw_uri: str, current_time: Optional[float] = None) -> Tuple[int, float]:
        now = current_time if current_time is not None else time.time()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fail_count, first_failed_at FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
            row = cursor.fetchone()
            if row:
                fail_count = row[0] + 1
                first_failed_at = row[1]
            else:
                fail_count = 1
                first_failed_at = now

            interval = self.backoff_schedule[min(fail_count - 1, len(self.backoff_schedule) - 1)]
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
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
            conn.commit()
            return cursor.rowcount > 0

    def get_due_for_retest(self, current_time: Optional[float] = None) -> List[Dict[str, Any]]:
        now = current_time if current_time is not None else time.time()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT unique_hash, raw_uri, fail_count, first_failed_at, next_check_at
                FROM degraded_proxies
                WHERE next_check_at <= ? AND status = 'degraded'
                """,
                (now,),
            ).fetchall()
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
        now = current_time if current_time is not None else time.time()
        cutoff = now - (max_age_hours * 3600)
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM degraded_proxies WHERE first_failed_at <= ?", (cutoff,))
            conn.commit()
            return cursor.rowcount
