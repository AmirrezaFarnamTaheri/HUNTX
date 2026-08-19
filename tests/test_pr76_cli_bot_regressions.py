"""CLI/bot regressions found while addressing PR #76 review feedback."""

import inspect
import sqlite3
from types import SimpleNamespace

from huntx.bot.interactive import InteractiveBot
from huntx.cli.main import _cmd_reset, _restore_bot_users
from huntx.state.db import open_db
from huntx.store import paths


def _set_temp_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    state_dir = data_dir / "state"
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "RAW_STORE_DIR", data_dir / "raw")
    monkeypatch.setattr(paths, "ARTIFACT_STORE_DIR", data_dir / "artifacts")
    monkeypatch.setattr(paths, "REJECTS_DIR", data_dir / "rejects")
    monkeypatch.setattr(paths, "STATE_DIR", state_dir)
    monkeypatch.setattr(paths, "LOGS_DIR", data_dir / "logs")
    monkeypatch.setattr(paths, "OUTPUT_DIR", data_dir / "outputs")
    monkeypatch.setattr(paths, "DEV_OUTPUT_DIR", data_dir / "outputs_dev")
    monkeypatch.setattr(paths, "STATE_DB_PATH", state_dir / "state.db")
    paths.ensure_dirs()
    return data_dir, state_dir


def test_reset_backup_survives_state_directory_deletion(monkeypatch, tmp_path):
    data_dir, state_dir = _set_temp_paths(monkeypatch, tmp_path)
    db = open_db(state_dir / "state.db")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, registered_at) VALUES ('1', '1', 1.0)"
        )

    _cmd_reset(SimpleNamespace(yes=True))

    backup_path = data_dir / "state.db.bak"
    assert backup_path.exists(), "reset must not delete the backup it just created"
    with sqlite3.connect(backup_path) as backup_conn:
        assert backup_conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_bot_init_tables_contains_no_shadow_schema_ddl(tmp_path):
    source = inspect.getsource(InteractiveBot._init_tables).upper()
    assert "CREATE TABLE" not in source
    assert "ALTER TABLE" not in source

    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    bot._init_tables()


def test_user_count_does_not_label_pending_users_as_muted(tmp_path):
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")

    with bot.db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO bot_users
                (user_id, chat_id, registered_at, approved, muted)
            VALUES (?, ?, 1.0, ?, ?)
            """,
            [
                ("pending", "pending", 0, 0),
                ("active", "active", 1, 0),
                ("muted", "muted", 1, 1),
            ],
        )

    assert bot._get_user_count() == {"total": 3, "active": 1, "muted": 1}


def test_restore_upsert_preserves_delivery_foreign_key_rows(tmp_path):
    db_path = tmp_path / "state.db"
    db = open_db(db_path)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users
                (user_id, chat_id, username, registered_at, approved)
            VALUES ('42', '42', 'old', 1.0, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO bot_delivery_items
                (user_id, artifact_hash, artifact_name, delivered_at)
            VALUES ('42', 'hash-1', 'artifact.txt', 2.0)
            """
        )

    _restore_bot_users(
        db_path,
        [
            {
                "user_id": "42",
                "chat_id": "42",
                "username": "new",
                "registered_at": 1.0,
                "approved": 1,
                "muted": 0,
                "last_delivered_at": 0.0,
                "default_format": "npvt",
            }
        ],
    )

    with db.connect() as conn:
        user = conn.execute(
            "SELECT chat_id, username FROM bot_users WHERE user_id = '42'"
        ).fetchone()
        delivery_count = conn.execute(
            "SELECT COUNT(*) AS c FROM bot_delivery_items WHERE user_id = '42'"
        ).fetchone()["c"]

    assert (user["chat_id"], user["username"]) == ("42", "new")
    assert delivery_count == 1
