import time
import sqlite3
from typing import Dict, Any, List, Optional, Tuple


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

    def _init_db(self):
        conn = self._get_conn()
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
        """
        Records a proxy failure and calculates next retry timestamp based on exponential backoff.
        """
        now = current_time or time.time()
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT fail_count, first_failed_at FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
        row = cursor.fetchone()


        if row:
            fail_count = row[0] + 1
            first_failed_at = row[1]
        else:
            fail_count = 1
            first_failed_at = now

        # Select backoff interval based on fail_count index
        backoff_idx = min(fail_count - 1, len(self.backoff_schedule) - 1)
        interval = self.backoff_schedule[backoff_idx]
        next_check = now + interval

        cursor.execute("""
            INSERT INTO degraded_proxies (unique_hash, raw_uri, fail_count, first_failed_at, next_check_at, status)
            VALUES (?, ?, ?, ?, ?, 'degraded')
            ON CONFLICT(unique_hash) DO UPDATE SET
                fail_count = excluded.fail_count,
                next_check_at = excluded.next_check_at,
                status = 'degraded'
        """, (unique_hash, raw_uri, fail_count, first_failed_at, next_check))
        conn.commit()
        return fail_count, next_check


    def reinstate_proxy(self, unique_hash: str) -> bool:
        """
        Reinstates a recovered proxy to active status by removing it from degraded state.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM degraded_proxies WHERE unique_hash = ?", (unique_hash,))
        conn.commit()
        return cursor.rowcount > 0

    def get_due_for_retest(self, current_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Returns list of degraded proxies due for re-testing.
        """
        now = current_time or time.time()
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT unique_hash, raw_uri, fail_count, first_failed_at, next_check_at
            FROM degraded_proxies
            WHERE next_check_at <= ? AND status = 'degraded'
        """, (now,))
        rows = cursor.fetchall()
        return [
            {
                "unique_hash": r[0],
                "raw_uri": r[1],
                "fail_count": r[2],
                "first_failed_at": r[3],
                "next_check_at": r[4],
            }
            for r in rows
        ]

    def purge_stale_proxies(self, max_age_hours: int = 48, current_time: Optional[float] = None) -> int:
        """
        Purges degraded proxies that have remained unreachable for > max_age_hours (default 48h).
        """
        now = current_time or time.time()
        cutoff = now - (max_age_hours * 3600)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM degraded_proxies WHERE first_failed_at <= ?", (cutoff,))
        conn.commit()
        return cursor.rowcount

