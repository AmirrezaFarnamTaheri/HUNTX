"""Guard the exact observation-key seek required by production-scale builds.

The source-first CROSS JOIN is correct only when record observations can be
looked up via a persistent index. An automatic/temporary index on multi-GB
historical state can cost longer than the global release deadline.
"""

import pytest

from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.verdict_store import get_records_for_governed_build


def test_records_have_persistent_observation_seek_index_on_restored_state(tmp_path):
    path = tmp_path / "state.db"
    db = open_db(path)
    with db.connect() as conn:
        index_names = {row["name"] for row in conn.execute("PRAGMA index_list(records)")}
        assert "idx_records_observation" in index_names
        columns = [
            row["name"] for row in conn.execute("PRAGMA index_info(idx_records_observation)")
        ]
        assert columns[:2] == ["source_observation_id", "is_active"]
        # Simulate a persisted database produced before the index existed.
        conn.execute("DROP INDEX idx_records_observation")

    reopened = open_db(path)
    with reopened.connect() as conn:
        assert any(
            row["name"] == "idx_records_observation"
            for row in conn.execute("PRAGMA index_list(records)")
        )


@pytest.mark.parametrize("governed", [False, True])
def test_build_queries_seek_exact_observations_without_autoindex(tmp_path, governed):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    with repo.db.connect() as conn:
        conn.execute("PRAGMA automatic_index=OFF")
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, "
            "ingested_at, status) VALUES (?, ?, ?, ?, 'processed')",
            [
                ("approved", f"file-{n}", f"sha-{n}", "2026-11-21 12:00:00")
                for n in range(50)
            ],
        )
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json) VALUES (?, ?, ?, ?, ?)",
            [
                (f"sha-{n}", n + 1, "npvt", f"identity-{n}", '{"line":"vless://fixture"}')
                for n in range(50)
            ],
        )
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT r.id FROM seen_files s "
            "CROSS JOIN records r INDEXED BY idx_records_observation "
            "WHERE s.source_id = ? AND s.ingested_at >= ? "
            "AND r.source_observation_id = s.id "
            "AND r.record_type = ? AND r.is_active = 1",
            ("approved", "2026-11-20 00:00:00", "npvt"),
        ).fetchall()
        assert any(
            "SEARCH r" in row["detail"] and "idx_records_observation" in row["detail"]
            for row in plan
        ), [row["detail"] for row in plan]

    if governed:
        result = get_records_for_governed_build(
            repo.db, ["npvt"], ["approved"], min_ingested_at="2026-11-20 00:00:00"
        )
    else:
        result = repo.get_records_for_build(
            ["npvt"], ["approved"], min_ingested_at="2026-11-20 00:00:00"
        )
    assert len(result) == 50
