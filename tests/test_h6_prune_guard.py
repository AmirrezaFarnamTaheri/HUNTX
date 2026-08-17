"""
H-6 Prune Guard Regression Suite.

Verifies that _cmd_prune / prune_old_data never deletes raw blobs still
referenced by active (is_active=1) records of blob-dependent formats.

The guard is inside StateRepo.prune_old_data via the `still_referenced`
sub-query.  We exercise it through the repo directly (no subprocess).
"""
import sqlite3
import tempfile
import pathlib
import time
import pytest

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


SCHEMA_PATH = (
    pathlib.Path(__file__).parent.parent
    / "src" / "huntx" / "state" / "schema.sql"
)


def _make_db() -> tuple[str, object]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = open_db(pathlib.Path(tmp.name))
    return tmp.name, db


def _ts_old(days=40):
    """Return ISO datetime N days in the past (older than default prune window)."""
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() - days * 86400),
    )


def _seed_seen_file(conn, source_id, external_id, raw_hash, ingested_at, status="processed"):
    conn.execute(
        """INSERT OR IGNORE INTO seen_files
           (source_id, external_id, raw_hash, ingested_at, status)
           VALUES (?, ?, ?, ?, ?)""",
        (source_id, external_id, raw_hash, ingested_at, status),
    )


def _seed_active_record(conn, raw_hash, record_type, unique_hash):
    conn.execute(
        """INSERT INTO records
           (source_file_hash, record_type, unique_hash, is_active)
           VALUES (?, ?, ?, 1)""",
        (raw_hash, record_type, unique_hash),
    )


def _seed_inactive_record(conn, raw_hash, record_type, unique_hash):
    conn.execute(
        """INSERT INTO records
           (source_file_hash, record_type, unique_hash, is_active)
           VALUES (?, ?, ?, 0)""",
        (raw_hash, record_type, unique_hash),
    )


# ---------------------------------------------------------------------------
# Test 1: blobs with active blob-dependent records are NOT returned for deletion
# ---------------------------------------------------------------------------

def test_prune_skips_blobs_with_active_blob_dependent_records():
    """H-6: prune_old_data must NOT return raw_hash for blobs still referenced
    by active records of blob-dependent formats (e.g. ovpn, nm, ehi, hc)."""
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src1", "ext1", "aaa111", old_ts)
        # This blob is still referenced by an active ovpn record
        _seed_active_record(conn, "aaa111", "ovpn", "unique_ovpn_1")
        conn.commit()

    result = repo.prune_old_data(days=30)

    assert "aaa111" not in result["raw_hashes"], (
        "H-6: aaa111 must NOT be eligible for deletion — active ovpn record references it"
    )
    assert result["seen_files"] == 0, (
        "H-6: seen_files row must not be deleted while active record references the blob"
    )


# ---------------------------------------------------------------------------
# Test 2: blobs with ONLY inactive records ARE eligible for deletion
# ---------------------------------------------------------------------------

def test_prune_allows_blobs_with_only_inactive_records():
    """H-6: blobs whose only records are is_active=0 may be pruned."""
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src2", "ext2", "bbb222", old_ts)
        _seed_inactive_record(conn, "bbb222", "ovpn", "unique_ovpn_2")
        conn.commit()

    result = repo.prune_old_data(days=30)

    assert "bbb222" in result["raw_hashes"], (
        "H-6: bbb222 must be eligible for deletion — only inactive records reference it"
    )


# ---------------------------------------------------------------------------
# Test 3: blobs with NO records at all are eligible for deletion
# ---------------------------------------------------------------------------

def test_prune_allows_blobs_with_no_records():
    """H-6: orphan blobs (no records at all) must be eligible for prune."""
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src3", "ext3", "ccc333", old_ts)
        # No records inserted
        conn.commit()

    result = repo.prune_old_data(days=30)

    assert "ccc333" in result["raw_hashes"], (
        "H-6: orphan blob ccc333 (no records) must be eligible for prune"
    )


# ---------------------------------------------------------------------------
# Test 4: recent blobs (within prune window) are NOT pruned regardless
# ---------------------------------------------------------------------------

def test_prune_skips_recent_blobs():
    """H-6: blobs ingested within the prune window are never pruned."""
    _, db = _make_db()
    repo = StateRepo(db)

    with db.connect() as conn:
        # Ingested 1 day ago — well within 30-day window
        recent_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 86400))
        _seed_seen_file(conn, "src4", "ext4", "ddd444", recent_ts)
        conn.commit()

    result = repo.prune_old_data(days=30)
    assert "ddd444" not in result["raw_hashes"], (
        "H-6: recently ingested blob must not be in prune candidates"
    )


# ---------------------------------------------------------------------------
# Test 5: all blob-dependent format types are guarded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["ovpn", "nm", "ehi", "hc", "hat", "sip", "dark", "npv4", "opaque_bundle"])
def test_all_blob_dependent_formats_are_guarded(fmt):
    """H-6: each blob-dependent format must protect its blob from pruning."""
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)
    raw_hash = f"hash_{fmt}_protected"

    with db.connect() as conn:
        _seed_seen_file(conn, f"src_{fmt}", f"ext_{fmt}", raw_hash, old_ts)
        _seed_active_record(conn, raw_hash, fmt, f"unique_{fmt}")
        conn.commit()

    result = repo.prune_old_data(days=30)
    assert raw_hash not in result["raw_hashes"], (
        f"H-6: blob protected by active {fmt!r} record must not be pruned"
    )
