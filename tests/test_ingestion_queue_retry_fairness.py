from types import SimpleNamespace

from huntx.state.db import open_db
from huntx.state.ingestion_queue import PersistentIngestionQueue


def _source(source_id: str):
    return SimpleNamespace(id=source_id, type="telegram_user")


def test_future_retry_in_newest_window_yields_to_older_ready_window(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        [_source("a")],
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )

    newest = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert newest is not None
    assert newest.window_end_ts == seed["anchor_ts"]
    queue.fail(
        newest.id,
        "run",
        "temporary failure",
        lease_token=newest.lease_token,
        retry_delay=600,
        now=10_000,
    )

    older = queue.claim_next("run", lease_seconds=60, now=10_001)
    assert older is not None
    assert older.window_end_ts < newest.window_end_ts


def test_due_retry_regains_lifo_priority(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        [_source("a")],
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )

    newest = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert newest is not None
    queue.fail(
        newest.id,
        "run",
        "temporary failure",
        lease_token=newest.lease_token,
        retry_delay=10,
        now=10_000,
    )

    retried = queue.claim_next("run", lease_seconds=60, now=10_011)
    assert retried is not None
    assert retried.id == newest.id
    assert retried.window_end_ts == seed["anchor_ts"]
