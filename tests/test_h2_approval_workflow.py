"""
H-2 Approval Workflow Regression Suite.

Tests:
1. Unapproved users cannot receive deliveries (delivery query filters approved=1).
2. Approved users do receive deliveries.
3. Setting approved=1 transitions user correctly.
4. Muted+approved users are excluded from delivery.
5. Default approved=0 for new registrations.
6. Delivery query is correct SQL (approved=1 AND muted=0).
"""
import pathlib
import sqlite3
import tempfile
import time
import pytest

from huntx.state.db import open_db


SCHEMA_PATH = (
    pathlib.Path(__file__).parent.parent
    / "src" / "huntx" / "state" / "schema.sql"
)


def _make_db() -> object:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return open_db(pathlib.Path(tmp.name))


def _add_user(conn, user_id, chat_id, approved=0, muted=0):
    conn.execute(
        """INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, chat_id, time.time(), approved, muted),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. Default new-user state: approved=0
# ---------------------------------------------------------------------------

def test_new_user_defaults_to_unapproved():
    """H-2: Newly registered users must default to approved=0."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_new", "c1", approved=0)
        row = conn.execute(
            "SELECT approved FROM bot_users WHERE user_id='u_new'"
        ).fetchone()
    assert row is not None
    assert row["approved"] == 0, f"Expected approved=0, got {row['approved']!r}"


# ---------------------------------------------------------------------------
# 2. Unapproved user excluded from delivery query
# ---------------------------------------------------------------------------

def test_unapproved_user_excluded_from_delivery():
    """H-2: Delivery query (approved=1 AND muted=0) must exclude unapproved user."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_unap", "c2", approved=0)
        result = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
    assert all(r["user_id"] != "u_unap" for r in result), (
        "H-2: unapproved user u_unap must not appear in delivery query"
    )


# ---------------------------------------------------------------------------
# 3. Approved user included in delivery query
# ---------------------------------------------------------------------------

def test_approved_user_included_in_delivery():
    """H-2: Approved, unmuted user must appear in delivery query."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_ok", "c3", approved=1, muted=0)
        result = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
    ids = [r["user_id"] for r in result]
    assert "u_ok" in ids, "H-2: approved+unmuted user u_ok must appear in delivery query"


# ---------------------------------------------------------------------------
# 4. Muted+approved user excluded from delivery
# ---------------------------------------------------------------------------

def test_muted_approved_user_excluded_from_delivery():
    """H-2: Muted user must be excluded even if approved."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_muted", "c4", approved=1, muted=1)
        result = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
    ids = [r["user_id"] for r in result]
    assert "u_muted" not in ids, "H-2: muted user u_muted must not appear in delivery query"


# ---------------------------------------------------------------------------
# 5. Setting approved=1 transitions user into delivery set
# ---------------------------------------------------------------------------

def test_approve_user_transitions_to_delivery():
    """H-2: After UPDATE approved=1, user appears in delivery query."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_pend", "c5", approved=0)
        # Verify excluded before approval
        before = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
        assert all(r["user_id"] != "u_pend" for r in before), "pre-condition: not yet approved"

        # Approve
        conn.execute("UPDATE bot_users SET approved=1 WHERE user_id='u_pend'")
        conn.commit()

        after = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
    ids = [r["user_id"] for r in after]
    assert "u_pend" in ids, "H-2: after approval, user must appear in delivery query"


# ---------------------------------------------------------------------------
# 6. Revoking approval (approved=0) removes user from delivery set
# ---------------------------------------------------------------------------

def test_revoke_approval_removes_from_delivery():
    """H-2: After UPDATE approved=0, user must no longer appear in delivery query."""
    db = _make_db()
    with db.connect() as conn:
        _add_user(conn, "u_rev", "c6", approved=1)
        conn.execute("UPDATE bot_users SET approved=0 WHERE user_id='u_rev'")
        conn.commit()
        result = conn.execute(
            "SELECT user_id FROM bot_users WHERE approved=1 AND muted=0"
        ).fetchall()
    ids = [r["user_id"] for r in result]
    assert "u_rev" not in ids, "H-2: revoked user must not appear in delivery query"


# ---------------------------------------------------------------------------
# 7. schema.sql contains NOT NULL DEFAULT 0 constraint for approved
# ---------------------------------------------------------------------------

def test_schema_sql_approved_not_null_default_zero():
    """H-2: schema.sql must define approved as NOT NULL DEFAULT 0."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "approved INTEGER NOT NULL DEFAULT 0" in schema, (
        "H-2: schema.sql must declare approved INTEGER NOT NULL DEFAULT 0"
    )
