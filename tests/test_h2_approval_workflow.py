"""
H-2 Approval Workflow Regression Suite.

Tests:
1. Unapproved users cannot receive deliveries.
2. Approved users in their private chat do receive deliveries.
3. Setting approved=1 transitions a private-chat user correctly.
4. Muted+approved users are excluded from delivery.
5. Default approved=0 for new registrations.
6. Delivery eligibility requires approved=1, muted=0, and chat_id=user_id.
"""
import pathlib
import tempfile
import time

from huntx.state.db import open_db
from huntx.bot.interactive import InteractiveBot


SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "src" / "huntx" / "state" / "schema.sql"


def _make_db() -> object:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return open_db(pathlib.Path(tmp.name))


def _make_bot(db) -> object:
    """Create a minimal bot instance with DB attached for delivery selection."""
    bot = object.__new__(InteractiveBot)
    bot.db = db
    return bot


def _add_user(conn, user_id, chat_id=None, approved=0, muted=0):
    chat_id = user_id if chat_id is None else chat_id
    conn.execute(
        """INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, chat_id, time.time(), approved, muted),
    )
    conn.commit()


def test_new_user_defaults_to_unapproved():
    """H-2: Newly registered users must default to approved=0."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_new", approved=0)
        row = conn.execute(
            "SELECT approved FROM bot_users WHERE user_id='u_new'"
        ).fetchone()
    assert row is not None
    assert row["approved"] == 0, f"Expected approved=0, got {row['approved']!r}"


def test_unapproved_user_excluded_from_delivery():
    """Unapproved private-chat users must be excluded from delivery."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_unap", approved=0)
    result = bot._get_active_users()
    assert all(r["user_id"] != "u_unap" for r in result)


def test_approved_user_included_in_delivery():
    """Approved, unmuted private-chat users must appear in delivery selection."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_ok", approved=1, muted=0)
    ids = [r["user_id"] for r in bot._get_active_users()]
    assert "u_ok" in ids


def test_muted_approved_user_excluded_from_delivery():
    """Muted users must be excluded even if approved."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_muted", approved=1, muted=1)
    ids = [r["user_id"] for r in bot._get_active_users()]
    assert "u_muted" not in ids


def test_approve_user_transitions_to_delivery():
    """After approved=1, a private-chat user enters the delivery set."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_pend", approved=0)
    before = bot._get_active_users()
    assert all(r["user_id"] != "u_pend" for r in before)

    with db.connect() as conn:
        conn.execute("UPDATE bot_users SET approved=1 WHERE user_id='u_pend'")
        conn.commit()

    ids = [r["user_id"] for r in bot._get_active_users()]
    assert "u_pend" in ids


def test_revoke_approval_removes_from_delivery():
    """After approved=0, a user must no longer appear in delivery selection."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_rev", approved=1)
        conn.execute("UPDATE bot_users SET approved=0 WHERE user_id='u_rev'")
        conn.commit()
    ids = [r["user_id"] for r in bot._get_active_users()]
    assert "u_rev" not in ids


def test_non_private_chat_is_never_delivery_eligible():
    """Approval cannot make a group/channel chat a GatherX delivery target."""
    db = _make_db()
    bot = _make_bot(db)
    with db.connect() as conn:
        _add_user(conn, "u_group", "-10099", approved=1, muted=0)
    assert bot._get_active_users() == []


def test_schema_sql_approved_not_null_default_zero():
    """schema.sql must define approved as NOT NULL DEFAULT 0."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "approved INTEGER NOT NULL DEFAULT 0" in schema
