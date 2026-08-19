"""H-6 prune safety regression suite."""

import pathlib
import tempfile
import time
from types import SimpleNamespace

import pytest

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "src" / "huntx" / "state" / "schema.sql"


def _make_db() -> tuple[str, object]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = open_db(pathlib.Path(tmp.name))
    return tmp.name, db


def _ts_old(days=40):
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


def test_prune_skips_blobs_with_active_blob_dependent_records():
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src1", "ext1", "aaa111", old_ts)
        _seed_active_record(conn, "aaa111", "ovpn", "unique_ovpn_1")

    result = repo.prune_old_data(days=30)

    assert "aaa111" not in result["raw_hashes"]
    assert result["seen_files"] == 0


def test_prune_allows_blobs_with_only_inactive_records():
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src2", "ext2", "bbb222", old_ts)
        _seed_inactive_record(conn, "bbb222", "ovpn", "unique_ovpn_2")

    result = repo.prune_old_data(days=30)
    assert "bbb222" in result["raw_hashes"]


def test_prune_allows_blobs_with_no_records():
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)

    with db.connect() as conn:
        _seed_seen_file(conn, "src3", "ext3", "ccc333", old_ts)

    result = repo.prune_old_data(days=30)
    assert "ccc333" in result["raw_hashes"]


def test_prune_skips_recent_blobs():
    _, db = _make_db()
    repo = StateRepo(db)

    with db.connect() as conn:
        recent_ts = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.gmtime(time.time() - 86400),
        )
        _seed_seen_file(conn, "src4", "ext4", "ddd444", recent_ts)

    result = repo.prune_old_data(days=30)
    assert "ddd444" not in result["raw_hashes"]


@pytest.mark.parametrize(
    "fmt",
    ["ovpn", "nm", "ehi", "hc", "hat", "sip", "dark", "npv4", "opaque_bundle"],
)
def test_all_blob_dependent_formats_are_guarded(fmt):
    _, db = _make_db()
    repo = StateRepo(db)
    old_ts = _ts_old(40)
    raw_hash = f"hash_{fmt}_protected"

    with db.connect() as conn:
        _seed_seen_file(conn, f"src_{fmt}", f"ext_{fmt}", raw_hash, old_ts)
        _seed_active_record(conn, raw_hash, fmt, f"unique_{fmt}")

    result = repo.prune_old_data(days=30)
    assert raw_hash not in result["raw_hashes"]


def test_cmd_prune_rechecks_live_hashes_before_deleting_disk_blobs(
    monkeypatch, tmp_path, capsys
):
    """The real CLI path must not delete a hash retained by another observation."""
    from huntx.cli.main import _cmd_prune
    from huntx.state.repo import StateRepo as ProductionStateRepo
    from huntx.store import paths
    from huntx.store.raw_store import RawStore

    live_hash = "a" * 64
    orphan_hash = "b" * 64
    deleted = []

    monkeypatch.setattr(paths, "STATE_DB_PATH", tmp_path / "state.db")
    monkeypatch.setattr(
        ProductionStateRepo,
        "prune_old_data",
        lambda self, days: {
            "records": 2,
            "seen_files": 1,
            "published_artifacts": 3,
            "raw_hashes": [live_hash, orphan_hash],
        },
    )
    monkeypatch.setattr(
        ProductionStateRepo,
        "get_all_known_hashes",
        lambda self: {live_hash},
    )
    monkeypatch.setattr(RawStore, "__init__", lambda self: None)

    def fake_prune_by_hashes(self, hashes):
        deleted.extend(hashes)
        return len(hashes)

    monkeypatch.setattr(RawStore, "prune_by_hashes", fake_prune_by_hashes)

    _cmd_prune(SimpleNamespace(days=30))

    assert deleted == [orphan_hash]
    output = capsys.readouterr().out
    assert "Raw hashes still referenced: 1" in output
    assert "Raw store files deleted: 1" in output
