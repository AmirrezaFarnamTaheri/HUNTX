#!/usr/bin/env python3
"""Validate and checkpoint HuntX durable runtime state.

The database is published only after every pending observation has a matching
content-addressed raw blob. Legacy databases created before raw-store syncing
are repaired conservatively: missing pending observations are removed and the
corresponding durable window (or legacy source offset) is rewound so the next
run downloads the data again.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _raw_path(raw_dir: Path, raw_hash: str) -> Path:
    return raw_dir / raw_hash[:2] / raw_hash


def _parse_window(metadata_json: Any) -> tuple[int, int] | None:
    if not metadata_json:
        return None
    try:
        metadata = json.loads(str(metadata_json))
        start = int(metadata["window_start_ts"])
        end = int(metadata["window_end_ts"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if end <= start:
        return None
    return start, end


def checkpoint_state(db_path: Path, raw_dir: Path) -> dict[str, Any]:
    if not db_path.is_file() or db_path.stat().st_size == 0:
        raise RuntimeError(f"state database is missing or empty: {db_path}")
    raw_dir.mkdir(parents=True, exist_ok=True)

    repaired_rows = 0
    rewound_windows = 0
    reset_sources: set[str] = set()
    released_leases = 0

    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        if _table_exists(conn, "ingestion_work_items"):
            now = int(time.time())
            cursor = conn.execute(
                """
                UPDATE ingestion_work_items
                SET status='partial', lease_owner=NULL, lease_expires_at=NULL,
                    next_retry_at=NULL, updated_at=?
                WHERE status='leased'
                """,
                (now,),
            )
            released_leases = int(cursor.rowcount)

        missing: list[sqlite3.Row] = []
        if _table_exists(conn, "seen_files"):
            rows = conn.execute("""
                SELECT id, source_id, raw_hash, metadata_json
                FROM seen_files
                WHERE status='pending'
                ORDER BY id
                """).fetchall()
            for row in rows:
                raw_hash = str(row["raw_hash"])
                if len(raw_hash) != 64 or not _raw_path(raw_dir, raw_hash).is_file():
                    missing.append(row)

        for row in missing:
            source_id = str(row["source_id"])
            window = _parse_window(row["metadata_json"])
            if window and _table_exists(conn, "ingestion_work_items"):
                start, end = window
                cursor = conn.execute(
                    """
                    UPDATE ingestion_work_items
                    SET status='pending', continuation_cursor=NULL,
                        lease_owner=NULL, lease_expires_at=NULL,
                        next_retry_at=NULL, completed_at=NULL,
                        last_error='rewound: referenced raw blob was unavailable',
                        updated_at=?
                    WHERE source_id=? AND window_start_ts=? AND window_end_ts=?
                    """,
                    (int(time.time()), source_id, start, end),
                )
                rewound_windows += max(0, int(cursor.rowcount))
            else:
                reset_sources.add(source_id)

            conn.execute("DELETE FROM seen_files WHERE id=?", (int(row["id"]),))
            repaired_rows += 1

        if reset_sources and _table_exists(conn, "source_state"):
            conn.executemany(
                "DELETE FROM source_state WHERE source_id=?",
                [(source_id,) for source_id in sorted(reset_sources)],
            )

        conn.commit()

    with sqlite3.connect(db_path, timeout=30, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        conn.execute("PRAGMA optimize")
        quick_check = conn.execute("PRAGMA quick_check").fetchone()
        if not quick_check or quick_check[0] != "ok":
            raise RuntimeError(f"state.db failed quick_check: {quick_check}")

        remaining_missing = 0
        if _table_exists(conn, "seen_files"):
            rows = conn.execute("SELECT raw_hash FROM seen_files WHERE status='pending'").fetchall()
            remaining_missing = sum(
                1
                for row in rows
                if len(str(row["raw_hash"])) != 64 or not _raw_path(raw_dir, str(row["raw_hash"])).is_file()
            )
        if remaining_missing:
            raise RuntimeError(f"{remaining_missing} pending observation(s) still reference missing raw blobs")

    return {
        "checkpoint": list(checkpoint) if checkpoint is not None else None,
        "quick_check": "ok",
        "released_leases": released_leases,
        "repaired_missing_pending_rows": repaired_rows,
        "rewound_windows": rewound_windows,
        "reset_legacy_sources": sorted(reset_sources),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(checkpoint_state(args.db, args.raw_dir), sort_keys=True))


if __name__ == "__main__":
    main()
