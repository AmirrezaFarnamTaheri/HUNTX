"""
H-1 Regression Suite — bot_users schema drift.

Verifies:
1. _restore_bot_users DDL contains 'approved' column (SSoT parity).
2. Round-trip backup->restore preserves approved status.
3. _restore_bot_users is idempotent on pre-existing DBs missing 'approved'.
4. schema.sql is the canonical DDL reference.
"""
import sqlite3
import tempfile
import pathlib
import os

from huntx.cli.main import _backup_bot_users, _restore_bot_users


def _open_fresh_db():
    """Return (path, conn) for a temp SQLite db with schema.sql applied."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    schema_path = (
        pathlib.Path(__file__).parent.parent
        / "src" / "huntx" / "state" / "schema.sql"
    )
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()
    return db_path, conn


def _insert_user(conn, user_id="u1", approved=1):
    conn.execute(
        "INSERT INTO bot_users (user_id, chat_id, registered_at, approved) "
        "VALUES (?, ?, ?, ?)",
        (user_id, "chat_" + user_id, 1_000_000.0, approved),
    )
    conn.commit()


def test_schema_sql_contains_approved_column():
    """H-1: schema.sql must define approved INTEGER NOT NULL DEFAULT 0."""
    schema_path = (
        pathlib.Path(__file__).parent.parent
        / "src" / "huntx" / "state" / "schema.sql"
    )
    assert schema_path.exists(), "schema.sql must exist"
    content = schema_path.read_text(encoding="utf-8")
    assert "approved" in content, "H-1: schema.sql bot_users must include approved column"


def test_restore_creates_approved_column_in_fresh_db():
    """H-1: _restore_bot_users must create table with approved column."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    data = [{
        "user_id": "u1", "chat_id": "c1", "registered_at": 1.0,
        "approved": 1, "muted": 0, "last_delivered_at": 0.0,
        "default_format": "npvt", "username": None,
    }]
    _restore_bot_users(db_path, data)
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(bot_users)").fetchall()}
    conn.close()
    assert "approved" in columns, "H-1: _restore_bot_users must create bot_users with approved column"


def test_round_trip_preserves_approved_true():
    """H-1: backup then restore must not drop approved=1."""
    db_path, conn = _open_fresh_db()
    _insert_user(conn, "u1", approved=1)
    conn.close()
    backed = _backup_bot_users(db_path)
    assert backed is not None and len(backed) == 1
    os.unlink(db_path)
    _restore_bot_users(db_path, backed)
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    row = conn2.execute("SELECT approved FROM bot_users WHERE user_id='u1'").fetchone()
    conn2.close()
    assert row is not None, "User u1 must survive restore"
    assert row["approved"] == 1, f"H-1: approved must be 1 after restore, got {row['approved']}"


def test_round_trip_preserves_approved_false():
    """H-1: backup then restore must not promote approved=0 to approved=1."""
    db_path, conn = _open_fresh_db()
    _insert_user(conn, "u2", approved=0)
    conn.close()
    backed = _backup_bot_users(db_path)
    os.unlink(db_path)
    _restore_bot_users(db_path, backed)
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    row = conn2.execute("SELECT approved FROM bot_users WHERE user_id='u2'").fetchone()
    conn2.close()
    assert row is not None
    assert row["approved"] == 0, f"H-1: approved=0 must survive restore as 0, got {row['approved']}"


def test_restore_is_idempotent_on_legacy_db_missing_approved():
    """H-1: _restore_bot_users must add approved to pre-existing DBs lacking it."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE bot_users (
            user_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            username TEXT,
            registered_at REAL NOT NULL,
            muted INTEGER DEFAULT 0,
            last_delivered_at REAL DEFAULT 0,
            default_format TEXT DEFAULT 'npvt'
        )
    """)
    conn.commit()
    conn.close()
    data = [{
        "user_id": "u3", "chat_id": "c3", "registered_at": 1.0,
        "muted": 0, "last_delivered_at": 0.0,
        "default_format": "npvt", "username": None,
    }]
    _restore_bot_users(db_path, data)
    conn2 = sqlite3.connect(db_path)
    columns = {row[1] for row in conn2.execute("PRAGMA table_info(bot_users)").fetchall()}
    conn2.close()
    assert "approved" in columns, "H-1: _restore_bot_users must ADD COLUMN approved to legacy DBs"


def test_backup_includes_approved_field():
    """H-1: _backup_bot_users output dicts must contain approved key."""
    db_path, conn = _open_fresh_db()
    _insert_user(conn, "u4", approved=1)
    conn.close()
    backed = _backup_bot_users(db_path)
    assert backed, "Backup must return data"
    assert "approved" in backed[0], "H-1: _backup_bot_users must include approved in each row dict"
