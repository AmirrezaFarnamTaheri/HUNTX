from __future__ import annotations

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

    Windows are LIFO by ``window_end_ts``. Within the same hour, the least
    recently updated source is selected first so dense sources cannot starve
    their peers. Every claim is leased and every page checkpoint can share the
    same transaction as raw observation inserts.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def floor_window(timestamp: float, window_seconds: int) -> int:
        return int(timestamp // window_seconds) * window_seconds

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

        current = time.time() if now is None else now
        anchor = self.floor_window(current, window_seconds) + window_seconds
        target_start = anchor - lookback_seconds
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
                while start < anchor:
                    before = conn.total_changes
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO ingestion_work_items (
                            campaign_id, source_id, source_type,
                            window_start_ts, window_end_ts,
                            status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
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
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'partial', lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE status = 'leased' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (current, current),
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
                SELECT * FROM ingestion_work_items
                WHERE status IN ('pending', 'partial', 'retry_wait')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY window_end_ts DESC, updated_at ASC, id ASC
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
                    int(row["continuation_cursor"])
                    if row["continuation_cursor"] is not None
                    else None
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
        cursor = conn.execute(
            """
            UPDATE ingestion_work_items
            SET continuation_cursor = ?, status = ?,
                items_ingested = items_ingested + ?,
                bytes_ingested = bytes_ingested + ?,
                lease_owner = NULL, lease_expires_at = NULL,
                next_retry_at = NULL, last_error = NULL,
                updated_at = ?, completed_at = ?
            WHERE id = ? AND status = 'leased' AND lease_owner = ?
            """,
            (
                continuation_cursor,
                status,
                max(0, int(items_ingested)),
                max(0, int(bytes_ingested)),
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
            conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'retry_wait', lease_owner = NULL, lease_expires_at = NULL,
                    next_retry_at = ?, last_error = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_owner = ?
                """,
                (
                    current + max(1, int(retry_delay)),
                    str(error)[:1000],
                    current,
                    int(item_id),
                    owner,
                ),
            )

    def release_owner(self, owner: str, *, now: Optional[int] = None) -> int:
        current = int(time.time()) if now is None else int(now)
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status = 'partial', lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE status = 'leased' AND lease_owner = ?
                """,
                (current, owner),
            )
            return int(cursor.rowcount)

    def summary(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM ingestion_work_items
                GROUP BY status
                """
            ).fetchall()
        result = {str(row["status"]): int(row["count"]) for row in rows}
        result["remaining"] = sum(
            count
            for status, count in result.items()
            if status in {"pending", "partial", "leased", "retry_wait"}
        )
        return result
