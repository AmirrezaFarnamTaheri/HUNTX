from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class IngestionWorkItem:
    id: int
    campaign_id: int
    source_id: str
    source_type: str
    window_start_ts: int
    window_end_ts: int
    continuation_cursor: Optional[int]
    attempt_count: int
    items_ingested: int
    bytes_ingested: int


class PersistentIngestionQueue:
    """SQLite-backed newest-window-first ingestion queue.

    Only closed, epoch-aligned windows are seeded. Windows are strict LIFO by
    ``window_end_ts``. Within the newest incomplete window, ``rotation_seq`` is
    advanced after every page so sources rotate deterministically even when
    several operations complete within the same wall-clock second.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def floor_window(timestamp: float, window_seconds: int) -> int:
        return int(timestamp // window_seconds) * window_seconds

    @staticmethod
    def _next_rotation_seq(conn: Any) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(rotation_seq), 0) + 1 AS next_seq " "FROM ingestion_work_items"
        ).fetchone()
        return int(row["next_seq"] if row else 1)

    def seed_rolling_horizon(
        self,
        sources: Iterable[Any],
        *,
        now: Optional[float] = None,
        lookback_seconds: int = 48 * 3600,
        window_seconds: int = 3600,
    ) -> dict[str, int]:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if lookback_seconds <= 0:
            raise ValueError("lookback_seconds must be positive")

        current = time.time() if now is None else float(now)
        if not math.isfinite(current):
            raise ValueError("now must be finite")

        # The anchor is the most recent fully closed boundary. The active
        # window [anchor, anchor + window_seconds) is deliberately excluded.
        anchor = self.floor_window(current, window_seconds)
        window_count = max(1, math.ceil(lookback_seconds / window_seconds))
        target_start = anchor - window_count * window_seconds
        created_at = int(current)
        inserted = 0

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ingestion_campaigns
                    (anchor_ts, target_start_ts, window_seconds, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (anchor, target_start, window_seconds, created_at, created_at),
            )
            row = conn.execute(
                """
                SELECT id FROM ingestion_campaigns
                WHERE anchor_ts = ? AND target_start_ts = ? AND window_seconds = ?
                """,
                (anchor, target_start, window_seconds),
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to create or load ingestion campaign")
            campaign_id = int(row["id"])

            for source in sources:
                if getattr(source, "type", None) != "telegram_user":
                    continue
                start = target_start
                while start + window_seconds <= anchor:
                    before = conn.total_changes
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO ingestion_work_items (
                            campaign_id, source_id, source_type,
                            window_start_ts, window_end_ts,
                            status, rotation_seq, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                        """,
                        (
                            campaign_id,
                            str(source.id),
                            str(source.type),
                            start,
                            start + window_seconds,
                            created_at,
                            created_at,
                        ),
                    )
                    inserted += conn.total_changes - before
                    start += window_seconds

        return {
            "campaign_id": campaign_id,
            "anchor_ts": anchor,
            "target_start_ts": target_start,
            "inserted": inserted,
        }

    def recover_expired_leases(self, *, now: Optional[int] = None) -> int:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            rotation_seq = self._next_rotation_seq(conn)
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'partial', lease_owner = NULL, lease_expires_at = NULL,
                    rotation_seq = ?, updated_at = ?
                WHERE status = 'leased' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (rotation_seq, current, current),
            )
            return int(cursor.rowcount)

    def claim_next(
        self,
        owner: str,
        *,
        lease_seconds: int,
        now: Optional[int] = None,
    ) -> Optional[IngestionWorkItem]:
        current = int(time.time()) if now is None else int(now)
        lease_expires = current + max(1, int(lease_seconds))

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                WITH newest_incomplete AS (
                    SELECT MAX(window_end_ts) AS window_end_ts
                    FROM ingestion_work_items
                    WHERE status IN ('pending', 'partial', 'retry_wait', 'leased')
                )
                SELECT work.*
                FROM ingestion_work_items AS work
                JOIN newest_incomplete AS newest
                  ON work.window_end_ts = newest.window_end_ts
                WHERE work.status IN ('pending', 'partial', 'retry_wait')
                  AND (work.next_retry_at IS NULL OR work.next_retry_at <= ?)
                ORDER BY work.rotation_seq ASC, work.id ASC
                LIMIT 1
                """,
                (current,),
            ).fetchone()
            if row is None:
                return None

            updated = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'leased', lease_owner = ?, lease_expires_at = ?,
                    attempt_count = attempt_count + 1, updated_at = ?
                WHERE id = ? AND status IN ('pending', 'partial', 'retry_wait')
                """,
                (owner, lease_expires, current, int(row["id"])),
            )
            if updated.rowcount != 1:
                return None

            return IngestionWorkItem(
                id=int(row["id"]),
                campaign_id=int(row["campaign_id"]),
                source_id=str(row["source_id"]),
                source_type=str(row["source_type"]),
                window_start_ts=int(row["window_start_ts"]),
                window_end_ts=int(row["window_end_ts"]),
                continuation_cursor=(
                    int(row["continuation_cursor"]) if row["continuation_cursor"] is not None else None
                ),
                attempt_count=int(row["attempt_count"]) + 1,
                items_ingested=int(row["items_ingested"]),
                bytes_ingested=int(row["bytes_ingested"]),
            )

    def checkpoint_page(
        self,
        item_id: int,
        owner: str,
        *,
        continuation_cursor: Optional[int],
        items_ingested: int,
        bytes_ingested: int,
        completed: bool,
        conn: Any,
        now: Optional[int] = None,
    ) -> None:
        current = int(time.time()) if now is None else int(now)
        status = "completed" if completed else "partial"
        completed_at = current if completed else None
        rotation_seq = self._next_rotation_seq(conn)
        cursor = conn.execute(
            """
            UPDATE ingestion_work_items
            SET continuation_cursor = ?, status = ?,
                items_ingested = items_ingested + ?,
                bytes_ingested = bytes_ingested + ?,
                lease_owner = NULL, lease_expires_at = NULL,
                next_retry_at = NULL, last_error = NULL,
                rotation_seq = ?, updated_at = ?, completed_at = ?
            WHERE id = ? AND status = 'leased' AND lease_owner = ?
            """,
            (
                continuation_cursor,
                status,
                max(0, int(items_ingested)),
                max(0, int(bytes_ingested)),
                rotation_seq,
                current,
                completed_at,
                int(item_id),
                owner,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"work item {item_id} lease was lost before checkpoint")

    def fail(
        self,
        item_id: int,
        owner: str,
        error: str,
        *,
        retry_delay: int,
        now: Optional[int] = None,
    ) -> None:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            rotation_seq = self._next_rotation_seq(conn)
            conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'retry_wait', lease_owner = NULL, lease_expires_at = NULL,
                    next_retry_at = ?, last_error = ?, rotation_seq = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_owner = ?
                """,
                (
                    current + max(1, int(retry_delay)),
                    str(error)[:1000],
                    rotation_seq,
                    current,
                    int(item_id),
                    owner,
                ),
            )

    def mark_terminal(
        self,
        item_id: int,
        owner: str,
        reason: str,
        *,
        now: Optional[int] = None,
    ) -> None:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'quarantined', lease_owner = NULL, lease_expires_at = NULL,
                    next_retry_at = NULL, last_error = ?, updated_at = ?, completed_at = ?
                WHERE id = ? AND status = 'leased' AND lease_owner = ?
                """,
                (str(reason)[:1000], current, current, int(item_id), owner),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"work item {item_id} lease was lost before terminalization")

    def terminalize_source(
        self,
        source_id: str,
        reason: str,
        *,
        now: Optional[int] = None,
    ) -> int:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'quarantined', lease_owner = NULL, lease_expires_at = NULL,
                    next_retry_at = NULL, last_error = ?, updated_at = ?, completed_at = ?
                WHERE source_id = ?
                  AND status IN ('pending', 'partial', 'retry_wait')
                """,
                (str(reason)[:1000], current, current, str(source_id)),
            )
            return int(cursor.rowcount)

    def release_owner(self, owner: str, *, now: Optional[int] = None) -> int:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            rotation_seq = self._next_rotation_seq(conn)
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'partial', lease_owner = NULL, lease_expires_at = NULL,
                    rotation_seq = ?, updated_at = ?
                WHERE status = 'leased' AND lease_owner = ?
                """,
                (rotation_seq, current, owner),
            )
            return int(cursor.rowcount)

    def summary(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) AS count
                FROM ingestion_work_items
                GROUP BY status
                """).fetchall()
        result = {str(row["status"]): int(row["count"]) for row in rows}
        result["remaining"] = sum(
            count for status, count in result.items() if status in {"pending", "partial", "leased", "retry_wait"}
        )
        return result
