"""Retention must honor shared blobs and exact observation foreign keys."""

import pytest

from huntx.state import StateRepo
from huntx.state.db import open_db
from huntx.store.raw_store import RawStore


@pytest.mark.parametrize("blob_formats", [None, ()])
def test_processed_cleanup_preserves_blob_needed_by_pending_observation(tmp_path, blob_formats):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    if blob_formats is not None:
        repo._BLOB_DEPENDENT_FORMATS = blob_formats
    store = RawStore(tmp_path / "raw")
    payload = b"shared local fixture"
    digest = store.save(payload)
    repo.record_file("first", "1", digest, len(payload), "fixture.txt", status="processed")
    second = repo.record_file("second", "1", digest, len(payload), "fixture.txt")

    assert digest not in repo.get_processed_hashes()
    assert store.prune_processed(repo) == 0
    assert store.get(digest) == payload

    repo.update_observation_status(second, "processed")
    assert store.prune_processed(repo) == 1
    assert not store.exists(digest)


@pytest.mark.parametrize("fresh_record", [False, True])
def test_age_prune_honors_observation_foreign_keys(tmp_path, fresh_record):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    digest = "a" * 64
    observation = repo.record_file("local", "1", digest, 1, "fixture.txt", status="processed")
    repo.add_record(digest, "npvt", "b" * 64, {"line": "local fixture"}, source_observation_id=observation)
    with repo.db.connect() as conn:
        conn.execute("UPDATE seen_files SET ingested_at = '2000-01-01 00:00:00'")
        if not fresh_record:
            conn.execute("UPDATE records SET created_at = '2000-01-01 00:00:00'")

    result = repo.prune_old_data(30)

    assert result["records"] == (0 if fresh_record else 1)
    assert result["seen_files"] == (0 if fresh_record else 1)
    assert result["raw_hashes"] == ([] if fresh_record else [digest])
    with repo.db.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == int(fresh_record)
        assert conn.execute("SELECT COUNT(*) FROM seen_files").fetchone()[0] == int(fresh_record)
    assert repo.prune_old_data(30)["seen_files"] == 0
