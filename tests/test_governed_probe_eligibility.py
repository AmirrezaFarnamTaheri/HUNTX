"""Governed SQL export must enforce the same probe safety rules as policy objects."""

import json

import pytest

from huntx.state.db import open_db
from huntx.state.verdict_store import (
    get_records_for_governed_build,
    upsert_record_verdict,
)


@pytest.mark.parametrize(
    ("state", "expires_at", "loose", "fresh"),
    [
        ("pass", 1200.0, True, True),
        ("unknown", None, True, False),
        ("unknown", 999.0, False, False),
        ("fail", 1200.0, False, False),
        ("expired", 1200.0, False, False),
        ("pass", 999.0, False, False),
        ("pass", None, False, False),
        ("invalid-status", 1200.0, False, False),
    ],
)
def test_secure_build_never_publishes_failed_or_expired_probe(
    tmp_path, state, expires_at, loose, fresh,
):
    db = open_db(tmp_path / "state.db")
    unique_hash = "a" * 64
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO seen_files (source_id, external_id, raw_hash, status) "
            "VALUES ('approved', 'item', ?, 'processed')",
            ("f" * 64,),
        )
        observation_id = int(conn.execute(
            "SELECT id FROM seen_files WHERE source_id = 'approved'"
        ).fetchone()["id"])
        conn.execute(
            "INSERT INTO records (source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json) VALUES (?, ?, ?, ?, ?)",
            ("f" * 64, observation_id, "npvt", unique_hash, json.dumps({"line": "test"})),
        )
    upsert_record_verdict(
        db,
        unique_hash=unique_hash,
        record_type="npvt",
        syntax_status="pass",
        parser_version="test",
        probe_status=state,
        probe_expires_at=expires_at,
        policy_status="pass",
        policy_version="test",
        policy_tier="secure",
    )
    for require_fresh_probe, expected in ((False, loose), (True, fresh)):
        exported = get_records_for_governed_build(
            db, ["npvt"], ["approved"],
            publication_tier="secure",
            require_fresh_probe=require_fresh_probe,
            now_epoch=1000.0,
        )
        assert bool(exported) is expected
        if expected:
            assert exported[0]["unique_hash"] == unique_hash
