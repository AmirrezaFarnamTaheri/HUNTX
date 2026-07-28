import asyncio
import base64
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from huntx.pipeline.ingest import IngestionPipeline
from huntx.state import StateRepo
from huntx.state.db import DBConnection


def test_pipeline_commits_acknowledgement_after_source_state():
    events = []
    state_repo = Mock()
    state_repo.get_source_state.return_value = {}
    state_repo.update_source_state.side_effect = lambda *args, **kwargs: events.append("state")

    class Connector:
        def list_new(self, state):
            return []

        def get_state(self):
            return {"offset": 7}

        def commit_acknowledgement(self):
            events.append("ack")

    asyncio.run(IngestionPipeline(Mock(), state_repo).run("source", Connector()))
    assert events == ["state", "ack"]


def test_pipeline_does_not_commit_acknowledgement_when_state_write_fails():
    state_repo = Mock()
    state_repo.get_source_state.return_value = {}
    state_repo.update_source_state.side_effect = RuntimeError("state write failed")
    connector = Mock()
    connector.list_new.return_value = []
    connector.get_state.return_value = {"offset": 7}

    with pytest.raises(RuntimeError, match="state write failed"):
        asyncio.run(IngestionPipeline(Mock(), state_repo).run("source", connector))

    connector.commit_acknowledgement.assert_not_called()


def test_v9_migration_preserves_staged_telegram_updates(tmp_path):
    db_path = tmp_path / "legacy.db"
    fingerprint = "a" * 64
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE telegram_bot_updates (
                token_fingerprint TEXT NOT NULL,
                update_id INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                received_at REAL NOT NULL,
                PRIMARY KEY (token_fingerprint, update_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO telegram_bot_updates VALUES (?, ?, ?, ?)",
            (fingerprint, 42, '{"update_id":42}', 1.0),
        )
        conn.execute("PRAGMA user_version = 8")

    db = DBConnection(db_path)
    with db.connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        staged = conn.execute(
            "SELECT update_id FROM telegram_bot_updates WHERE token_fingerprint = ?",
            (fingerprint,),
        ).fetchall()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(telegram_bot_consumers)").fetchall()
        }

    assert version == 10
    assert [row["update_id"] for row in staged] == [42]
    assert columns == {
        "token_fingerprint",
        "consumer_id",
        "acknowledged_update_id",
        "active",
        "updated_at",
    }


def test_v10_migration_preserves_unrelated_verdict_cache(tmp_path):
    db_path = tmp_path / "vmess-v9.db"
    DBConnection(db_path)

    legacy_value = {"v": "2", "add": "example.com", "port": "443", "ps": "legacy"}
    legacy_json = json.dumps(legacy_value, separators=(",", ":"))
    legacy_uri = "vmess://" + base64.b64encode(legacy_json.encode()).decode()
    old_hash = hashlib.sha256(legacy_uri.encode()).hexdigest()

    canonical_value = dict(legacy_value)
    canonical_value.pop("ps")
    canonical_json = json.dumps(canonical_value, sort_keys=True, separators=(",", ":"))
    canonical_uri = "vmess://" + base64.b64encode(canonical_json.encode()).decode()
    new_hash = hashlib.sha256(canonical_uri.encode()).hexdigest()
    unrelated_hash = "f" * 64

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO records (
                source_file_hash, record_type, unique_hash, data_json, is_active
            ) VALUES (?, ?, ?, ?, 1)
            """,
            ("s" * 64, "npvt", old_hash, json.dumps({"line": legacy_uri})),
        )
        verdict = (
            "npvt",
            "valid",
            "1",
            "unknown",
            "allow",
            "1",
            "default",
            "[]",
            1.0,
        )
        conn.execute(
            """
            INSERT INTO record_verdicts (
                unique_hash, record_type, syntax_status, parser_version,
                probe_status, policy_status, policy_version, policy_tier,
                reason_codes_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (old_hash, *verdict),
        )
        conn.execute(
            """
            INSERT INTO record_verdicts (
                unique_hash, record_type, syntax_status, parser_version,
                probe_status, policy_status, policy_version, policy_tier,
                reason_codes_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (unrelated_hash, *verdict),
        )
        conn.execute("PRAGMA user_version = 9")

    db = DBConnection(db_path)
    with db.connect() as conn:
        record = conn.execute(
            "SELECT unique_hash, data_json FROM records WHERE source_file_hash = ?",
            ("s" * 64,),
        ).fetchone()
        verdict_hashes = {
            row["unique_hash"]
            for row in conn.execute("SELECT DISTINCT unique_hash FROM record_verdicts").fetchall()
        }

    assert record["unique_hash"] == new_hash
    assert json.loads(record["data_json"])["line"] == canonical_uri
    assert old_hash not in verdict_hashes
    assert new_hash in verdict_hashes
    assert unrelated_hash in verdict_hashes


def test_bot_inbox_pruning_is_fenced_by_slowest_active_consumer(tmp_path):
    repo = StateRepo(DBConnection(tmp_path / "state.db"))
    fingerprint = "b" * 64
    repo.store_bot_updates(
        fingerprint,
        [{"update_id": update_id} for update_id in range(1, 206)],
    )
    repo.register_bot_consumer(fingerprint, "chat:a", 0)
    repo.register_bot_consumer(fingerprint, "chat:b", 0)

    assert repo.acknowledge_bot_consumer(
        fingerprint,
        "chat:a",
        205,
        retain_last=0,
    ) == 0
    assert repo.acknowledge_bot_consumer(
        fingerprint,
        "chat:b",
        200,
        retain_last=0,
    ) == 200

    with repo.db.connect() as conn:
        remaining = [
            row["update_id"]
            for row in conn.execute(
                "SELECT update_id FROM telegram_bot_updates ORDER BY update_id"
            ).fetchall()
        ]

    assert remaining == [201, 202, 203, 204, 205]


def test_record_file_is_atomic_for_concurrent_duplicate_observations(tmp_path):
    repo = StateRepo(DBConnection(tmp_path / "state.db"))

    def record():
        return repo.record_file(
            "source",
            "external",
            "c" * 64,
            3,
            "item.bin",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        observation_ids = list(pool.map(lambda _: record(), range(16)))

    assert len(set(observation_ids)) == 1
    with repo.db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM seen_files WHERE source_id = ? AND external_id = ?",
            ("source", "external"),
        ).fetchone()["count"]
    assert count == 1


def test_direct_state_repo_import_receives_atomic_implementation():
    from huntx.state.repo import StateRepo as DirectStateRepo

    assert DirectStateRepo.record_file.__module__ == "huntx.state.repo_hardening"
