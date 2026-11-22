"""Regression coverage for the large restored-state observation join.

A 13+ database can lack the v5 index when imported/restored from a schema
snapshot, and stale SQLite planner estimates may choose an expensive type
index over an exact observation lookup. Both paths must remain safe.
"""

from contextlib import contextmanager

import pytest

from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.verdict_store import get_records_for_governed_build


def test_restored_versioned_database_reinstalls_observation_seek_index(tmp_path):
    path = tmp_path / "state.db"
    db = open_db(path)
    with db.connect() as conn:
        index_names = {row["name"] for row in conn.execute("PRAGMA index_list(records)")}
        assert "idx_records_observation" in index_names
        columns = [
            row["name"] for row in conn.execute("PRAGMA index_info(idx_records_observation)")
        ]
        assert columns[:2] == ["source_observation_id", "is_active"]
        # Simulate a valid already-versioned restored DB missing its v5 index.
        conn.execute("DROP INDEX idx_records_observation")

    reopened = open_db(path)
    with reopened.connect() as conn:
        assert any(
            row["name"] == "idx_records_observation"
            for row in conn.execute("PRAGMA index_list(records)")
        )


@pytest.mark.parametrize("governed", [False, True])
def test_build_queries_seek_observation_even_when_planner_stats_are_misleading(
    tmp_path, monkeypatch, governed
):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    with repo.db.connect() as conn:
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, "
            "ingested_at, status) VALUES (?, ?, ?, ?, 'processed')",
            [
                (
                    "approved" if n % 40 == 0 else "blocked",
                    f"file-{n}",
                    f"sha-{n}",
                    "2026-11-21 12:00:00" if n % 40 == 0 else "2026-10-01 00:00:00",
                )
                for n in range(2000)
            ],
        )
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json) VALUES (?, ?, ?, ?, ?)",
            [
                (f"sha-{n}", n + 1, "npvt", f"identity-{n}", '{"line":"vless://fixture"}')
                for n in range(2000)
            ],
        )
        conn.execute("ANALYZE")
        # Only 50 of 2,000 historical records have an approved recent
        # observation. Even with skewed statistics, the real build must
        # seek those IDs rather than scan the cumulative record inventory.
        conn.execute(
            "UPDATE sqlite_stat1 SET stat = '500000000 500000000 500000000' "
            "WHERE idx = 'idx_records_observation'"
        )
        conn.execute(
            "UPDATE sqlite_stat1 SET stat = '500000000 1 1 1 1 1' "
            "WHERE idx = 'idx_records_build'"
        )
        conn.execute("ANALYZE sqlite_master")

    # Production restores its existing state through open_db(), which must
    # replace the stale observation-index estimates before querying.
    repo = StateRepo(open_db(tmp_path / "state.db"))
    with repo.db.connect() as conn:
        refreshed = conn.execute(
            "SELECT stat FROM sqlite_stat1 "
            "WHERE idx = 'idx_records_observation'"
        ).fetchone()
        assert refreshed is not None
        assert not str(refreshed["stat"]).startswith("500000000 ")

    seen_sql = []
    original_connect = repo.db.connect

    @contextmanager
    def tracing_connect():
        with original_connect() as conn:
            conn.set_trace_callback(
                lambda sql: seen_sql.append(sql) if "WITH filtered AS" in sql else None
            )
            try:
                yield conn
            finally:
                conn.set_trace_callback(None)

    monkeypatch.setattr(repo.db, "connect", tracing_connect)
    if governed:
        result = get_records_for_governed_build(
            repo.db, ["npvt"], ["approved"], min_ingested_at="2026-11-20 00:00:00"
        )
    else:
        result = repo.get_records_for_build(
            ["npvt"], ["approved"], min_ingested_at="2026-11-20 00:00:00"
        )
    assert len(result) == 50
    assert seen_sql, "The production query must be captured for plan validation"
    with original_connect() as conn:
        plan = conn.execute("EXPLAIN QUERY PLAN " + seen_sql[-1]).fetchall()
    details = [row["detail"] for row in plan]
    assert any(
        "SEARCH r" in detail and "idx_records_observation" in detail
        for detail in details
    ), details


@pytest.mark.parametrize("governed", [False, True])
def test_build_query_uses_indexed_lifecycle_identity_lookup(tmp_path, monkeypatch, governed):
    """A large restored lifecycle table must never be scanned per record.

    Production's previous EXPLAIN showed 'CORRELATED SCALAR SUBQUERY; SCAN p',
    which blocked the entire release build until the deadline expired.
    """
    repo = StateRepo(open_db(tmp_path / "state.db"))
    count = 1300
    with repo.db.connect() as conn:
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, status) "
            "VALUES ('approved', ?, ?, 'processed')",
            [(f"item-{n}", f"raw-{n}") for n in range(count)],
        )
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json) VALUES (?, ?, 'npvt', ?, ?)",
            [
                (f"raw-{n}", n + 1, f"{n:064x}", '{"line":"vless://fixture"}')
                for n in range(count)
            ],
        )
        conn.executemany(
            "INSERT INTO proxy_lifecycle("
            "unique_hash, record_type, lifecycle_status, first_seen_at, last_seen_at"
            ") VALUES (?, 'npvt', ?, 1, 2)",
            [
                (f"{n:064x}", "revoked" if n % 20 == 0 else "active")
                for n in range(count)
            ],
        )
        conn.execute("ANALYZE")

    sql_queries = []
    original_connect = repo.db.connect

    @contextmanager
    def tracing_connect():
        with original_connect() as conn:
            conn.set_trace_callback(
                lambda sql: sql_queries.append(sql) if "WITH filtered AS" in sql else None
            )
            try:
                yield conn
            finally:
                conn.set_trace_callback(None)

    monkeypatch.setattr(repo.db, "connect", tracing_connect)
    if governed:
        rows = get_records_for_governed_build(repo.db, ["npvt"], ["approved"])
    else:
        rows = repo.get_records_for_build(["npvt"], ["approved"])

    assert len(rows) == count - (count + 19) // 20
    assert sql_queries
    # A named, forced lookup is stable even if restored sqlite_stat1 statistics
    # lead SQLite to cost the correlated full scan incorrectly.
    assert "INDEXED BY idx_proxy_lifecycle_build_lookup" in sql_queries[-1]
    with original_connect() as conn:
        explain = conn.execute("EXPLAIN QUERY PLAN " + sql_queries[-1]).fetchall()
    details = [row["detail"] for row in explain]
    assert any(
        "SEARCH p USING" in detail and "idx_proxy_lifecycle_build_lookup" in detail
        for detail in details
    ), details
    assert not any("SCAN p" in detail for detail in details), details
