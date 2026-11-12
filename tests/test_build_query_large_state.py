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
    assert len(rows) == total // 10
    assert all(row["data"]["line"].startswith("vless://") for row in rows)
