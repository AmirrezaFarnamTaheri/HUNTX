"""Large-state build reads must finish within the release's remaining budget.

A source-time filter should be applied before the historical record scan,
rather than scanning every record in a multi-gigabyte cumulative database.
"""

import json

import pytest

from huntx.core.deadline import Deadline
from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.verdict_store import get_records_for_governed_build


@pytest.mark.parametrize("governed", [False, True])
def test_large_stale_history_does_not_exhaust_short_build_budget(tmp_path, governed):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    total = 12000
    with repo.db.connect() as conn:
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, "
            "ingested_at, status) VALUES (?, ?, ?, ?, 'processed')",
            (
                (
                    f"src{n % 40}",
                    f"item{n}",
                    f"{n:064x}",
                    "2026-11-12 00:00:00" if n % 10 == 0
                    else "2026-10-01 00:00:00",
                )
                for n in range(total)
            ),
        )
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id,"
            "record_type, unique_hash, data_json) VALUES (?, ?, 'npvt', ?, ?)",
            (
                (f"{n:064x}", n + 1, f"{n:064x}", json.dumps({"line": f"vless://{n}"}))
                for n in range(total)
            ),
        )

    approved_sources = [f"src{i}" for i in range(30)]
    if governed:
        rows = get_records_for_governed_build(
            repo.db, ["npvt"], approved_sources,
            min_ingested_at="2026-11-11 00:00:00",
            deadline=Deadline(1.5),
        )
    else:
        rows = repo.get_records_for_build(
            ["npvt"], approved_sources,
            min_ingested_at="2026-11-11 00:00:00",
            deadline=Deadline(1.5),
        )
    assert len(rows) == (total // 10) * 3 // 4
    assert all(row["data"]["line"].startswith("vless://") for row in rows)


@pytest.mark.parametrize("governed", [False, True])
def test_recent_governed_reads_do_not_scan_stale_history(tmp_path, monkeypatch, governed):
    """Bound SQLite VM work, independent of runner CPU speed or wall-clock jitter.

    A fresh 900-row slice in 12k observations must not execute a historical
    full-record scan. The observed cost is checked for both normal and governed
    build reads, without changing source/identity eligibility.
    """
    from contextlib import contextmanager

    repo = StateRepo(open_db(tmp_path / "state.db"))
    total = 12000
    with repo.db.connect() as conn:
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, "
            "ingested_at, status) VALUES (?, ?, ?, ?, 'processed')",
            (
                (f"src{n % 40}", f"item{n}", f"{n:064x}",
                 "2026-11-12 00:00:00" if n % 10 == 0
                 else "2026-10-01 00:00:00")
                for n in range(total)
            ),
        )
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json) VALUES (?, ?, 'npvt', ?, ?)",
            (
                (f"{n:064x}", n + 1, f"{n:064x}",
                 json.dumps({"line": f"vless://{n}"}))
                for n in range(total)
            ),
        )

    steps = [0]
    original_connect = repo.db.connect

    @contextmanager
    def traced_connect():
        with original_connect() as conn:
            def progress():
                steps[0] += 1
                return 0

            conn.set_progress_handler(progress, 1000)
            try:
                yield conn
            finally:
                conn.set_progress_handler(None, 0)

    monkeypatch.setattr(repo.db, "connect", traced_connect)
    sources = [f"src{i}" for i in range(30)]
    if governed:
        rows = get_records_for_governed_build(
            repo.db, ["npvt"], sources, min_ingested_at="2026-11-11 00:00:00",
        )
    else:
        rows = repo.get_records_for_build(
            ["npvt"], sources, min_ingested_at="2026-11-11 00:00:00",
        )

    assert len(rows) == 900
    # This is a bound on SQLite progress callbacks (1000 VM opcodes each),
    # not elapsed seconds. The previous records-first plan exceeds 3000.
    assert steps[0] < 250, f"Build query scanned stale records: {steps[0]}k opcodes"
