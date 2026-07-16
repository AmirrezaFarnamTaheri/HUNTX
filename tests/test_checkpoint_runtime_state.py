import hashlib
import sqlite3
from pathlib import Path

from scripts.checkpoint_runtime_state import checkpoint_state


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE source_state (
                source_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                state_json TEXT,
                updated_at INTEGER
            );
            CREATE TABLE seen_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                external_id TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                metadata_json TEXT,
                status TEXT DEFAULT 'pending'
            );
            CREATE TABLE ingestion_work_items (
                id INTEGER PRIMARY KEY,
                source_id TEXT NOT NULL,
                window_start_ts INTEGER NOT NULL,
                window_end_ts INTEGER NOT NULL,
                continuation_cursor INTEGER,
                status TEXT NOT NULL,
                lease_owner TEXT,
                lease_expires_at INTEGER,
                next_retry_at INTEGER,
                last_error TEXT,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER
            );
            """
        )


def test_checkpoint_rewinds_missing_window_blob(tmp_path):
    db = tmp_path / "state.db"
    raw = tmp_path / "raw"
    _create_db(db)
    missing_hash = "a" * 64
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO ingestion_work_items
                (id, source_id, window_start_ts, window_end_ts,
                 continuation_cursor, status, updated_at)
            VALUES (1, 'source', 0, 3600, 99, 'completed', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO seen_files
                (source_id, external_id, raw_hash, metadata_json, status)
            VALUES ('source', '99', ?,
                    '{"window_start_ts": 0, "window_end_ts": 3600}', 'pending')
            """,
            (missing_hash,),
        )

    result = checkpoint_state(db, raw)

    with sqlite3.connect(db) as conn:
        work = conn.execute(
            "SELECT status, continuation_cursor FROM ingestion_work_items WHERE id=1"
        ).fetchone()
        seen = conn.execute("SELECT COUNT(*) FROM seen_files").fetchone()[0]
    assert work == ("pending", None)
    assert seen == 0
    assert result["repaired_missing_pending_rows"] == 1
    assert result["rewound_windows"] == 1


def test_checkpoint_releases_leases_and_accepts_present_blob(tmp_path):
    db = tmp_path / "state.db"
    raw = tmp_path / "raw"
    _create_db(db)
    data = b"durable"
    raw_hash = hashlib.sha256(data).hexdigest()
    blob = raw / raw_hash[:2] / raw_hash
    blob.parent.mkdir(parents=True)
    blob.write_bytes(data)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO ingestion_work_items
                (id, source_id, window_start_ts, window_end_ts,
                 continuation_cursor, status, lease_owner, lease_expires_at, updated_at)
            VALUES (1, 'source', 0, 3600, 99, 'leased', 'dead-run', 9999999999, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO seen_files
                (source_id, external_id, raw_hash, metadata_json, status)
            VALUES ('source', '99', ?, '{}', 'pending')
            """,
            (raw_hash,),
        )

    result = checkpoint_state(db, raw)

    with sqlite3.connect(db) as conn:
        work = conn.execute(
            "SELECT status, lease_owner FROM ingestion_work_items WHERE id=1"
        ).fetchone()
    assert work == ("partial", None)
    assert result["released_leases"] == 1
    assert result["quick_check"] == "ok"
