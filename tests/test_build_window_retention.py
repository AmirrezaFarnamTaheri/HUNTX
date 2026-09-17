"""Release membership is based on ingestion timestamps, never observation IDs."""

import datetime
from unittest.mock import patch

import pytest

from huntx.core.orchestrator import Orchestrator
from huntx.state import StateRepo
from huntx.state.db import open_db
from huntx.state.verdict_store import get_records_for_governed_build

CUTOFF = "2026-09-14 12:00:00"


@pytest.fixture
def repo(tmp_path):
    return StateRepo(open_db(tmp_path / "state.db"))


def observe(repo, name, timestamp, *, unique_hash=None):
    oid = repo.record_file("local", name, name + "-hash", 1, "fixture.txt", status="processed")
    repo.add_record(name + "-hash", "npvt", unique_hash or name, {"line": name}, source_observation_id=oid)
    with repo.db.connect() as conn:
        conn.execute("UPDATE seen_files SET ingested_at = ? WHERE id = ?", (timestamp, oid))
    return oid


def records(repo, governed):
    if governed:
        return get_records_for_governed_build(
            repo.db, ["npvt"], ["local"], min_ingested_at=CUTOFF,
        )
    return repo.get_records_for_build(["npvt"], ["local"], min_ingested_at=CUTOFF)


@pytest.mark.parametrize("governed", [False, True])
def test_exact_boundary_and_nonmonotonic_ids(repo, governed):
    observe(repo, "boundary", CUTOFF)
    observe(repo, "expired", "2026-09-14 11:59:59")
    observe(repo, "recent", "2026-09-16 00:00:00")
    assert [r["data"]["line"] for r in records(repo, governed)] == ["boundary", "recent"]


@pytest.mark.parametrize("governed", [False, True])
def test_refreshed_old_id_does_not_admit_unrelated_stale_rows(repo, governed):
    oid = observe(repo, "first", "2000-01-01 00:00:00")
    observe(repo, "stale", "2000-01-01 00:00:00")
    assert repo.record_file("local", "first", "changed", 1, "fixture.txt") == oid
    repo.add_record("changed", "npvt", "changed", {"line": "refreshed"}, source_observation_id=oid)
    with repo.db.connect() as conn:
        conn.execute("UPDATE seen_files SET ingested_at = ? WHERE id = ?", (CUTOFF, oid))
    assert [r["data"]["line"] for r in records(repo, governed)] == ["refreshed"]


@pytest.mark.parametrize("governed", [False, True])
def test_empty_window_does_not_resurrect_history(repo, governed):
    observe(repo, "expired", "2000-01-01 00:00:00")
    assert records(repo, governed) == []


@pytest.mark.parametrize("governed", [False, True])
def test_fresh_transformation_does_not_refresh_ingestion(repo, governed):
    observe(repo, "delayed", "2000-01-01 00:00:00")
    repo.prune_old_data(3)
    assert len(repo.get_records_for_build(["npvt"], ["local"])) == 1
    assert records(repo, governed) == []


@pytest.mark.parametrize("governed", [False, True])
def test_time_filter_applies_before_deduplication(repo, governed):
    observe(repo, "recent", CUTOFF, unique_hash="shared")
    observe(repo, "expired", "2000-01-01 00:00:00", unique_hash="shared")
    assert [r["data"]["line"] for r in records(repo, governed)] == ["recent"]


@pytest.mark.parametrize("governed", [False, True])
def test_database_failure_is_not_empty_success(repo, governed):
    with patch.object(repo.db, "connect", side_effect=RuntimeError("database unavailable")):
        with pytest.raises(RuntimeError, match="database unavailable"):
            records(repo, governed)


def test_cutoff_is_72_hours_before_fixed_utc_run_start(monkeypatch):
    monkeypatch.delenv("HUNTX_OUTPUT_RETENTION_DAYS", raising=False)
    orch = object.__new__(Orchestrator)
    start = datetime.datetime(2026, 9, 17, 12, tzinfo=datetime.timezone.utc)
    assert orch._get_build_window_start(start) == CUTOFF
    monkeypatch.setenv("HUNTX_OUTPUT_RETENTION_DAYS", "7")
    assert orch._get_build_window_start(start) == "2026-09-10 12:00:00"


@pytest.mark.parametrize("value", ["0", "-1", "bad", ""])
def test_invalid_retention_is_rejected_before_build(monkeypatch, value):
    monkeypatch.setenv("HUNTX_OUTPUT_RETENTION_DAYS", value)
    with pytest.raises(ValueError, match="positive integer"):
        object.__new__(Orchestrator)._get_build_window_start()
