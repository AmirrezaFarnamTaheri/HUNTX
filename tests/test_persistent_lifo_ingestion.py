from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import pytest

from huntx.connectors.telegram_user.windowed import WindowedTelegramUserConnector
from huntx.state.db import open_db
from huntx.state.ingestion_queue import PersistentIngestionQueue
from huntx.state.repo import StateRepo


def _sources(*ids: str):
    return [SimpleNamespace(id=source_id, type="telegram_user") for source_id in ids]


def test_seed_is_idempotent_and_claims_newest_closed_hour_first(tmp_path):
    queue = PersistentIngestionQueue(open_db(tmp_path / "state.db"))
    first = queue.seed_rolling_horizon(
        _sources("a", "b"),
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )
    second = queue.seed_rolling_horizon(
        _sources("a", "b"),
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )

    assert first["anchor_ts"] == 7200
    assert first["inserted"] == 4
    assert second["inserted"] == 0

    item = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert item is not None
    assert item.window_end_ts == first["anchor_ts"]
    assert item.window_end_ts <= 10_000


def test_exact_boundary_excludes_new_active_window(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        _sources("a"),
        now=10_800,
        lookback_seconds=3600,
        window_seconds=3600,
    )

    assert seed["anchor_ts"] == 10_800
    assert seed["target_start_ts"] == 7200
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT window_start_ts, window_end_ts FROM ingestion_work_items"
        ).fetchall()
    assert [(row["window_start_ts"], row["window_end_ts"]) for row in rows] == [
        (7200, 10_800)
    ]


def test_non_divisible_lookback_rounds_outward_to_aligned_closed_windows(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        _sources("a"),
        now=10_000,
        lookback_seconds=5400,
        window_seconds=3600,
    )

    assert seed["anchor_ts"] == 7200
    assert seed["target_start_ts"] == 0
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT window_start_ts, window_end_ts FROM ingestion_work_items ORDER BY window_start_ts"
        ).fetchall()
    assert [(row["window_start_ts"], row["window_end_ts"]) for row in rows] == [
        (0, 3600),
        (3600, 7200),
    ]
    assert all(row["window_end_ts"] <= seed["anchor_ts"] for row in rows)


def test_partial_page_rotates_sources_within_same_second(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        _sources("a", "b"),
        now=10_000,
        lookback_seconds=3600,
        window_seconds=3600,
    )

    first = queue.claim_next("run-a", lease_seconds=60, now=10_000)
    assert first is not None
    with db.connect() as conn:
        queue.checkpoint_page(
            first.id,
            "run-a",
            continuation_cursor=900,
            items_ingested=3,
            bytes_ingested=12,
            completed=False,
            conn=conn,
            now=10_000,
        )

    second = queue.claim_next("run-b", lease_seconds=60, now=10_000)
    assert second is not None
    assert second.window_end_ts == seed["anchor_ts"]
    assert second.source_id != first.source_id


def test_leased_newest_hour_blocks_older_hour(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    seed = queue.seed_rolling_horizon(
        _sources("only"),
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )

    newest = queue.claim_next("worker-a", lease_seconds=60, now=10_000)
    assert newest is not None
    assert newest.window_end_ts == seed["anchor_ts"]
    assert queue.claim_next("worker-b", lease_seconds=60, now=10_001) is None

    assert queue.release_owner("worker-a", now=10_002) == 1
    resumed = queue.claim_next("worker-b", lease_seconds=60, now=10_003)
    assert resumed is not None
    assert resumed.id == newest.id


def test_terminal_stale_work_does_not_block_older_windows(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    queue.seed_rolling_horizon(
        _sources("removed"),
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )
    newest = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert newest is not None
    queue.mark_terminal(newest.id, "run", "source removed", now=10_000)

    older = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert older is not None
    assert older.window_end_ts < newest.window_end_ts


def test_expired_lease_is_recovered_with_cursor_intact(tmp_path):
    db = open_db(tmp_path / "state.db")
    queue = PersistentIngestionQueue(db)
    queue.seed_rolling_horizon(
        _sources("a"),
        now=10_000,
        lookback_seconds=3600,
        window_seconds=3600,
    )
    item = queue.claim_next("dead-run", lease_seconds=10, now=10_000)
    assert item is not None

    assert queue.recover_expired_leases(now=10_011) == 1
    recovered = queue.claim_next("next-run", lease_seconds=60, now=10_012)
    assert recovered is not None
    assert recovered.id == item.id
    assert recovered.continuation_cursor is None


def test_file_insert_and_residue_checkpoint_roll_back_together(tmp_path):
    db = open_db(tmp_path / "state.db")
    repo = StateRepo(db)
    queue = PersistentIngestionQueue(db)
    queue.seed_rolling_horizon(
        _sources("a"),
        now=10_000,
        lookback_seconds=3600,
        window_seconds=3600,
    )
    item = queue.claim_next("run", lease_seconds=60, now=10_000)
    assert item is not None

    with pytest.raises(RuntimeError, match="force rollback"):
        with db.connect() as conn:
            repo.record_files_batch(
                [("a", "42", "hash", 3, "x.txt", "pending", "{}")],
                conn=conn,
            )
            queue.checkpoint_page(
                item.id,
                "run",
                continuation_cursor=42,
                items_ingested=1,
                bytes_ingested=3,
                completed=False,
                conn=conn,
                now=10_001,
            )
            raise RuntimeError("force rollback")

    assert not repo.has_seen_file("a", "42")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, continuation_cursor FROM ingestion_work_items WHERE id = ?",
            (item.id,),
        ).fetchone()
    assert row["status"] == "leased"
    assert row["continuation_cursor"] is None


def test_overlapping_campaigns_do_not_duplicate_source_windows(tmp_path):
    queue = PersistentIngestionQueue(open_db(tmp_path / "state.db"))
    first = queue.seed_rolling_horizon(
        _sources("a"),
        now=10_000,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )
    second = queue.seed_rolling_horizon(
        _sources("a"),
        now=13_600,
        lookback_seconds=2 * 3600,
        window_seconds=3600,
    )

    assert first["inserted"] == 2
    assert second["inserted"] == 1


class _AsyncMessages:
    def __init__(self, messages):
        self.messages = messages

    def __aiter__(self):
        async def generate():
            for message in self.messages:
                yield message

        return generate()


class _FakeClient:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    def iter_messages(self, peer, **kwargs):
        self.calls.append((peer, kwargs))
        offset_id = int(kwargs.get("offset_id") or 0)
        messages = [message for message in self.messages if not offset_id or message.id < offset_id]
        limit = int(kwargs["limit"])
        return _AsyncMessages(messages[:limit])


class _WindowConnector(WindowedTelegramUserConnector):
    def __init__(self, client):
        self._fake_client = client
        self.peer = "peer"

    def _client(self):
        return self._fake_client

    async def _ensure_connected_async(self, client):
        return None

    async def _resolve_peer_async(self, peer_entity, client=None):
        return peer_entity


class _Message:
    def __init__(self, message_id: int, timestamp: int, text: str):
        self.id = message_id
        self.date = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        self.message = text
        self.document = None
        self.photo = None
        self.video = None
        self.gif = None
        self.sticker = None
        self.voice = None
        self.audio = None
        self.video_note = None


def test_window_page_resumes_exclusively_without_duplicates():
    messages = [
        _Message(5, 4_900, "five"),
        _Message(4, 4_800, "four"),
        _Message(3, 4_700, "three"),
        _Message(2, 3_500, "too old"),
    ]
    connector = _WindowConnector(_FakeClient(messages))

    first = asyncio.run(
        connector.fetch_window_page(
            window_start_ts=4_000,
            window_end_ts=5_000,
            continuation_cursor=None,
            limit=2,
        )
    )
    second = asyncio.run(
        connector.fetch_window_page(
            window_start_ts=4_000,
            window_end_ts=5_000,
            continuation_cursor=first.continuation_cursor,
            limit=2,
        )
    )

    assert [item.external_id for item in first.items] == ["5", "4"]
    assert first.continuation_cursor == 4
    assert not first.completed
    assert [item.external_id for item in second.items] == ["3"]
    assert second.continuation_cursor is None
    assert second.completed
