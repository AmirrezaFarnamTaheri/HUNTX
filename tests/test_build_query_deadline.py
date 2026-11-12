"""Bounded build-query contracts for large persisted HUNTX state.

An expired release deadline must stop SQLite work, not turn it into
an empty/approved build or leave a worker running past the budget.
"""

import json

import pytest

from huntx.core.deadline import Deadline, DeadlineExceeded
from huntx.pipeline.build import BuildPipeline
from huntx.state.db import open_db
from huntx.state.repo import StateRepo


def test_expired_build_query_fails_closed(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))

    with pytest.raises(DeadlineExceeded, match="build"):
        repo.get_records_for_build(
            ["npvt"], ["approved"], deadline=Deadline(0)
        )


def test_build_query_interrupts_after_sql_started(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    with repo.db.connect() as conn:
        rows = [
            ("approved", f"file-{n}", f"{n:064x}", "processed")
            for n in range(1600)
        ]
        conn.executemany(
            "INSERT INTO seen_files(source_id, external_id, raw_hash, status)"
            " VALUES (?, ?, ?, ?)",
            rows,
        )
        observations = conn.execute(
            "SELECT id, raw_hash FROM seen_files ORDER BY id"
        ).fetchall()
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id,"
            " record_type, unique_hash, data_json) VALUES (?, ?, 'npvt', ?, ?)",
            [
                (row["raw_hash"], row["id"], row["raw_hash"], json.dumps({"line": "vless://x"}))
                for row in observations
            ],
        )

    class ExpiresInsideQuery(Deadline):
        def __init__(self):
            super().__init__(3600)
            self.calls = 0

        def expired(self):
            self.calls += 1
            return self.calls > 1

    deadline = ExpiresInsideQuery()
    with pytest.raises(DeadlineExceeded, match="build"):
        repo.get_records_for_build(
            ["npvt"], ["approved"], deadline=deadline
        )
    assert deadline.calls > 1


def test_build_pipeline_propagates_deadline_to_sql_query():
    from unittest.mock import Mock

    state_repo = Mock()
    state_repo.get_records_for_build.return_value = []
    pipeline = BuildPipeline(state_repo, Mock(), Mock())
    deadline = Deadline(60)

    assert pipeline.run({
        "name": "all_sources",
        "formats": ["npvt"],
        "from_sources": ["approved"],
    }, deadline=deadline) == []
    state_repo.get_records_for_build.assert_called_once_with(
        ["npvt"], ["approved"], min_seen_file_id=None, deadline=deadline
    )


def test_expired_governed_query_fails_closed(tmp_path):
    from huntx.state.verdict_store import get_records_for_governed_build

    repo = StateRepo(open_db(tmp_path / "state.db"))
    with pytest.raises(DeadlineExceeded, match="build"):
        get_records_for_governed_build(
            repo.db, ["npvt"], ["approved"], deadline=Deadline(0)
        )
