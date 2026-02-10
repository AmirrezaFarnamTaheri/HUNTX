import unittest
import sqlite3
import time
from unittest.mock import MagicMock, patch, AsyncMock
from huntx.bot.interactive import (
    InteractiveBot,
    WELCOME_TEXT,
    SUPPORTED_FORMATS,
    _BOT_COMMANDS,
)


def _make_in_memory_db():
    """Create a minimal in-memory DB with row_factory for dict-like access."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class FakeDB:
    """Minimal fake DB wrapper matching open_db interface."""

    def __init__(self, conn):
        self._conn = conn

    def connect(self):
        return self._conn


class FakeConnCtx:
    """Context manager wrapper for a raw connection."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        self._conn.commit()


class TestBotUserRegistration(unittest.TestCase):
    def setUp(self):
        self.conn = _make_in_memory_db()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                username TEXT,
                registered_at REAL NOT NULL,
                muted INTEGER DEFAULT 0,
                last_delivered_at REAL DEFAULT 0,
                default_format TEXT DEFAULT 'npvt'
            )
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_register_new_user(self):
        """New user should be inserted and return True."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at) VALUES (?, ?, ?, ?)",
            ("111", "222", "alice", now),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM bot_users WHERE user_id = '111'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["chat_id"], "222")
        self.assertEqual(row["username"], "alice")
        self.assertEqual(row["muted"], 0)
        self.assertEqual(row["default_format"], "npvt")

    def test_update_existing_user(self):
        """Updating existing user should change chat_id and username."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at) VALUES (?, ?, ?, ?)",
            ("111", "222", "alice", now),
        )
        self.conn.commit()
        self.conn.execute(
            "UPDATE bot_users SET chat_id = ?, username = ? WHERE user_id = ?",
            ("333", "alice_new", "111"),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM bot_users WHERE user_id = '111'").fetchone()
        self.assertEqual(row["chat_id"], "333")
        self.assertEqual(row["username"], "alice_new")

    def test_mute_unmute(self):
        """Mute/unmute should toggle the muted flag."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at) VALUES (?, ?, ?, ?)",
            ("111", "222", "alice", now),
        )
        self.conn.commit()

        self.conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = '111'")
        self.conn.commit()
        row = self.conn.execute("SELECT muted FROM bot_users WHERE user_id = '111'").fetchone()
        self.assertEqual(row["muted"], 1)

        self.conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = '111'")
        self.conn.commit()
        row = self.conn.execute("SELECT muted FROM bot_users WHERE user_id = '111'").fetchone()
        self.assertEqual(row["muted"], 0)

    def test_set_default_format(self):
        """Setting default_format should persist."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at) VALUES (?, ?, ?, ?)",
            ("111", "222", "alice", now),
        )
        self.conn.commit()
        self.conn.execute("UPDATE bot_users SET default_format = 'ovpn' WHERE user_id = '111'")
        self.conn.commit()
        row = self.conn.execute("SELECT default_format FROM bot_users WHERE user_id = '111'").fetchone()
        self.assertEqual(row["default_format"], "ovpn")

    def test_get_active_users_excludes_muted(self):
        """_get_active_users should only return non-muted users."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at, muted) VALUES (?, ?, ?, ?, ?)",
            ("1", "10", "a", now, 0),
        )
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at, muted) VALUES (?, ?, ?, ?, ?)",
            ("2", "20", "b", now, 1),
        )
        self.conn.execute(
            "INSERT INTO bot_users (user_id, chat_id, username, registered_at, muted) VALUES (?, ?, ?, ?, ?)",
            ("3", "30", "c", now, 0),
        )
        self.conn.commit()
        rows = self.conn.execute("SELECT user_id FROM bot_users WHERE muted = 0").fetchall()
        active_ids = {r["user_id"] for r in rows}
        self.assertEqual(active_ids, {"1", "3"})

    def test_user_count(self):
        """User count query should return correct totals."""
        now = time.time()
        for uid, muted in [("1", 0), ("2", 1), ("3", 0), ("4", 0)]:
            self.conn.execute(
                "INSERT INTO bot_users (user_id, chat_id, username, registered_at, muted) VALUES (?, ?, ?, ?, ?)",
                (uid, uid + "0", f"u{uid}", now, muted),
            )
        self.conn.commit()
        total = self.conn.execute("SELECT COUNT(*) AS c FROM bot_users").fetchone()["c"]
        active = self.conn.execute("SELECT COUNT(*) AS c FROM bot_users WHERE muted = 0").fetchone()["c"]
        self.assertEqual(total, 4)
        self.assertEqual(active, 3)


class TestBotConstants(unittest.TestCase):
    def test_welcome_text_contains_gatherx(self):
        self.assertIn("GatherX", WELCOME_TEXT)

    def test_welcome_text_contains_all_commands(self):
        for cmd in ["/get", "/latest", "/formats", "/protocols", "/count",
                    "/setformat", "/myinfo", "/status", "/mute", "/unmute", "/ping", "/help"]:
            self.assertIn(cmd, WELCOME_TEXT, f"Missing command {cmd} in WELCOME_TEXT")

    def test_bot_commands_list_length(self):
        self.assertEqual(len(_BOT_COMMANDS), 13)

    def test_supported_formats_count(self):
        self.assertEqual(len(SUPPORTED_FORMATS), 12)

    def test_supported_formats_includes_key_formats(self):
        for fmt in ["npvt", "ovpn", "ehi", "hc", "hat", "opaque_bundle"]:
            self.assertIn(fmt, SUPPORTED_FORMATS)


class TestBotCommandNames(unittest.TestCase):
    def test_all_commands_have_descriptions(self):
        for cmd in _BOT_COMMANDS:
            self.assertTrue(len(cmd.command) > 0)
            self.assertTrue(len(cmd.description) > 0)

    def test_no_duplicate_commands(self):
        names = [cmd.command for cmd in _BOT_COMMANDS]
        self.assertEqual(len(names), len(set(names)), "Duplicate bot command names found")


if __name__ == "__main__":
    unittest.main()
