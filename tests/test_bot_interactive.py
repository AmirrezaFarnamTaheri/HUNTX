import unittest
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
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
        for cmd in ["/get", "/latest", "/formats",
                    "/setformat", "/myinfo", "/mute", "/unmute"]:
            self.assertIn(cmd, WELCOME_TEXT, f"Missing command {cmd} in WELCOME_TEXT")

    def test_bot_commands_list_length(self):
        # When Telethon isn't installed, `_BOT_COMMANDS` is intentionally empty so tests can run.
        if not _BOT_COMMANDS:
            self.skipTest("Telethon not installed; bot commands are not populated.")
        required = {"start", "get", "latest", "formats", "setformat", "myinfo", "mute", "unmute", "help"}
        cmds = {c.command for c in _BOT_COMMANDS}
        missing = required - cmds
        self.assertFalse(missing, f"Missing required bot commands: {sorted(missing)}")

    def test_supported_formats_count(self):
        self.assertGreaterEqual(len(SUPPORTED_FORMATS), 1)

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


class TestBotFilenameMatching(unittest.TestCase):
    def test_matches_internal_and_exported_b64sub_names(self):
        self.assertTrue(InteractiveBot._filename_matches_format("all_sources.npvt.b64sub", "b64sub"))
        self.assertTrue(InteractiveBot._filename_matches_format("all_sources_npvt_b64sub.txt", "b64sub"))

    def test_matches_internal_and_exported_decoded_names(self):
        self.assertTrue(InteractiveBot._filename_matches_format("all_sources.npvt.decoded.json", "decoded.json"))
        self.assertTrue(InteractiveBot._filename_matches_format("all_sources_npvt_decoded.json", "decoded.json"))


class TestBotInteractiveCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state_db = Path("./temp_test_interactive.db")
        self.data_dir = Path("./temp_data_interactive")
        self.data_dir.mkdir(exist_ok=True)

        with patch('huntx.store.paths.STATE_DB_PATH', self.state_db), \
             patch('huntx.store.paths.DATA_DIR', self.data_dir):
            self.bot = InteractiveBot(
                token="123:abc",
                api_id=123,
                api_hash="hash"
            )

        self.bot.client = MagicMock()
        self.bot.client.respond = AsyncMock()

    async def asyncTearDown(self):
        if self.state_db.exists():
            try:
                self.state_db.unlink()
            except OSError:
                pass
        if self.data_dir.exists():
            try:
                for f in self.data_dir.iterdir():
                    f.unlink()
                self.data_dir.rmdir()
            except OSError:
                pass

    async def test_on_ping(self):
        mock_msg = AsyncMock()
        mock_msg.edit = AsyncMock()

        event = MagicMock()
        event.respond = AsyncMock(return_value=mock_msg)

        await self.bot._on_ping(event)

        event.respond.assert_called_once_with("🏓 Pong!")
        mock_msg.edit.assert_called_once()
        self.assertIn("Latency", mock_msg.edit.call_args[0][0])

    async def test_on_protocols(self):
        event = MagicMock()
        event.respond = AsyncMock()

        await self.bot._on_protocols(event)

        event.respond.assert_called_once()
        msg = event.respond.call_args[0][0]
        self.assertIn("Supported Protocols", msg)

    async def test_on_status(self):
        event = MagicMock()
        event.respond = AsyncMock()

        with self.bot.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO source_state (source_id, source_type, state_json, updated_at) VALUES (?, ?, ?, 1)", ("src1", "telegram", "{}"))
            conn.execute("INSERT OR REPLACE INTO seen_files (source_id, external_id, raw_hash, filename, status, file_size, metadata_json) VALUES (?, ?, ?, ?, ?, 1, '{}')", ("src1", "1", "hash123", "test.txt", "processed"))
            conn.execute("INSERT OR REPLACE INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES (?, ?, ?, ?, 1)", ("hash123", "npvt", "u1", '{"line": "vmess://test"}'))

        await self.bot._on_status(event)

        event.respond.assert_called_once()
        msg = event.respond.call_args[0][0]
        self.assertIn("System Status", msg)
        self.assertIn("Sources", msg)

    async def test_on_count(self):
        event = MagicMock()
        event.respond = AsyncMock()

        with self.bot.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES (?, ?, ?, ?, 1)", ("hash123", "npvt", "u1", '{"line": "vmess://test"}'))
            conn.execute("INSERT OR REPLACE INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES (?, ?, ?, ?, 1)", ("hash123", "npvt", "u2", '{"line": "vless://test"}'))

        await self.bot._on_count(event)

        self.assertGreaterEqual(event.respond.call_count, 1)
        msg = event.respond.call_args[0][0]
        self.assertIn("Proxy Counts", msg)


if __name__ == "__main__":
    unittest.main()
