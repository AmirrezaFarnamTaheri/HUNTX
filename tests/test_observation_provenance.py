from __future__ import annotations

import json

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


def test_build_trust_is_bound_to_the_exact_source_observation(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    raw_hash = "a" * 64

    approved_id = repo.record_file("approved", "1", raw_hash, 7, "same.txt")
    quarantined_id = repo.record_file("quarantined", "2", raw_hash, 7, "same.txt")
    repo.add_records_batch(
        [
            (
                raw_hash,
                quarantined_id,
                "fmt",
                "record-1",
                json.dumps({"value": "untrusted"}),
            )
        ]
    )

    assert approved_id != quarantined_id
    assert repo.get_records_for_build(["fmt"], ["approved"]) == []
    assert repo.get_records_for_build(["fmt"], ["quarantined"]) == [
        {"record_type": "fmt", "data": {"value": "untrusted"}}
    ]


def test_observation_status_updates_do_not_cross_sources_with_same_blob(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    raw_hash = "b" * 64

    first_id = repo.record_file("source-a", "1", raw_hash, 7, "same.txt")
    second_id = repo.record_file("source-b", "2", raw_hash, 7, "same.txt")
    repo.update_observation_status(first_id, "failed", "bad source")

    with repo.db.connect() as conn:
        rows = conn.execute("SELECT id, status, error_msg FROM seen_files ORDER BY id").fetchall()

    assert [(row["id"], row["status"], row["error_msg"]) for row in rows] == [
        (first_id, "failed", "bad source"),
        (second_id, "pending", None),
    ]


def test_changed_external_item_is_requeued_and_old_records_are_retired(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    first_hash = "c" * 64
    second_hash = "d" * 64

    observation_id = repo.record_file("source-a", "message-1", first_hash, 3, "old.txt")
    repo.add_records_batch(
        [
            (
                first_hash,
                observation_id,
                "fmt",
                "old-record",
                json.dumps({"version": 1}),
            )
        ]
    )
    repo.update_observation_status(observation_id, "processed")

    same_observation_id = repo.record_file("source-a", "message-1", second_hash, 4, "new.txt")

    assert same_observation_id == observation_id
    with repo.db.connect() as conn:
        observation = conn.execute(
            "SELECT raw_hash, filename, status FROM seen_files WHERE id = ?",
            (observation_id,),
        ).fetchone()
        active = conn.execute(
            "SELECT is_active FROM records WHERE source_observation_id = ?",
            (observation_id,),
        ).fetchone()
    assert tuple(observation) == (second_hash, "new.txt", "pending")
    assert active["is_active"] == 0
