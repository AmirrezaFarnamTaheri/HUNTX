import unittest
import sqlite3
import time
import os
import shutil
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from huntx.state.db import DBConnection, open_db
from huntx.state.repo import StateRepo
from huntx.store.raw_store import RawStore
from huntx.bot.interactive import InteractiveBot

class TestElevation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test.db"
        self.raw_dir = self.temp_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        
        # Override paths to use our temp dirs
        self.patch_data_dir = patch("huntx.store.paths.DATA_DIR", self.temp_dir)
        self.patch_db_path = patch("huntx.store.paths.STATE_DB_PATH", self.db_path)
        self.patch_raw_dir = patch("huntx.store.paths.RAW_STORE_DIR", self.raw_dir)
        self.patch_data_dir.start()
        self.patch_db_path.start()
        self.patch_raw_dir.start()
        
        self.db = open_db(self.db_path)
        self.repo = StateRepo(self.db)
        self.raw_store = RawStore(base_dir=self.raw_dir)

    def tearDown(self):
        self.patch_data_dir.stop()
        self.patch_db_path.stop()
        self.patch_raw_dir.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Database schema and migration optimizations
    def test_schema_indexes_exist(self):
        """Verify new performance-critical indexes exist automatically on initialization."""
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row["name"] for row in cursor.fetchall()]
            self.assertIn("idx_seen_files_hash", indexes)
            self.assertIn("idx_records_hash", indexes)
            self.assertIn("idx_seen_files_status", indexes)

    # 2. Database and raw store auto-pruning
    def test_auto_pruning_workflow(self):
        """Verify prune_old_data and prune_by_hashes work seamlessly."""
        # Insert mock seen_files and records
        with self.db.connect() as conn:
            # 1. Old seen file and record (ingested 31 days ago)
            conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, ingested_at, status) VALUES (?, ?, ?, datetime('now', '-31 days'), 'success')",
                ("s1", "ext1", "oldhash1",)
            )
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, created_at, data_json) VALUES (?, 'npvt', 'uniq1', datetime('now', '-31 days'), '{\"line\":\"vmess://foo\"}')",
                ("oldhash1",)
            )
            conn.execute(
                "INSERT INTO published_artifacts (route_name, artifact_hash, published_at) VALUES (?, ?, datetime('now', '-31 days'))",
                ("route1", "arthash1")
            )
            
            # 2. New seen file and record (ingested 1 day ago)
            conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, ingested_at, status) VALUES (?, ?, ?, datetime('now', '-1 days'), 'success')",
                ("s1", "ext2", "newhash2",)
            )
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, created_at, data_json) VALUES (?, 'npvt', 'uniq2', datetime('now', '-1 days'), '{\"line\":\"vless://bar\"}')",
                ("newhash2",)
            )
            conn.execute(
                "INSERT INTO published_artifacts (route_name, artifact_hash, published_at) VALUES (?, ?, datetime('now', '-1 days'))",
                ("route1", "arthash2")
            )

        # Create old raw blob file on disk
        old_blob_dir = self.raw_dir / "ol"
        old_blob_dir.mkdir(parents=True, exist_ok=True)
        old_blob_path = old_blob_dir / "oldhash1"
        old_blob_path.write_bytes(b"old blob content")
        self.assertTrue(old_blob_path.exists())

        # Perform pruning of items older than 30 days
        prune_res = self.repo.prune_old_data(30)
        self.assertEqual(prune_res["seen_files"], 1)
        self.assertEqual(prune_res["records"], 1)
        self.assertEqual(prune_res["published_artifacts"], 1)
        self.assertEqual(prune_res["raw_hashes"], ["oldhash1"])

        # Prune raw store files
        raw_pruned = self.raw_store.prune_by_hashes(prune_res["raw_hashes"])
        self.assertEqual(raw_pruned, 1)
        self.assertFalse(old_blob_path.exists())

    # 3. Dynamic settings keyboard formatting in telethon bot
    @patch("huntx.bot.interactive.TelegramClient")
    def test_settings_keyboard_checkmarks(self, mock_client):
        """Verify _build_setformat_keyboard returns inline checkmark next to chosen format."""
        bot = InteractiveBot("token", 123, "hash")
        
        # Register user1 first so preference update works
        bot._register_user("user1", "chat1")
        
        # Test when default is npvt
        bot._set_user_pref("user1", "npvt")
        buttons = bot._build_setformat_keyboard("user1")
        
        # npvt is the first button in first row
        npvt_btn = buttons[0][0]
        self.assertTrue(npvt_btn.text.startswith("✅"))
        
        # Change preferred format to b64sub
        bot._set_user_pref("user1", "b64sub")
        buttons = bot._build_setformat_keyboard("user1")
        b64sub_btn = buttons[0][1]
        self.assertTrue(b64sub_btn.text.startswith("✅"))

    # 4. Optimized SQLite JSON Count Query Verification
    @patch("huntx.bot.interactive.TelegramClient")
    def test_optimized_protocol_counts(self, mock_client):
        """Verify _get_protocol_counts gets the correct counts per protocol."""
        bot = InteractiveBot("token", 123, "hash")
        
        # Insert mock npvt records with json line payloads matching various schemes
        with bot.db.connect() as conn:
            conn.execute("DELETE FROM records") # Clear existing
            
            # vmess
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES ('h1', 'npvt', 'u1', '{\"line\":\"vmess://a\"}', 1)"
            )
            # vless
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES ('h1', 'npvt', 'u2', '{\"line\":\"vless://b\"}', 1)"
            )
            # wireguard
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES ('h1', 'npvt', 'u3', '{\"line\":\"wg://c\"}', 1)"
            )
            # non-npvt format (should count under record_type)
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES ('h1', 'ovpn', 'u4', '{\"line\":\"ovpn_content\"}', 1)"
            )
            # Inactive record (should be ignored)
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, is_active) VALUES ('h1', 'npvt', 'u5', '{\"line\":\"vmess://d\"}', 0)"
            )
            
        counts = bot._get_protocol_counts()
        self.assertEqual(counts.get("vmess"), 1)
        self.assertEqual(counts.get("vless"), 1)
        self.assertEqual(counts.get("wg"), 1)
        self.assertEqual(counts.get("ovpn"), 1)

    # 5. Admin command room and security checks
    @patch("huntx.bot.interactive.TelegramClient")
    def test_admin_checking_logic(self, mock_client):
        """Verify _is_admin correctly identifies configured admin users."""
        bot = InteractiveBot("token", 123, "hash")
        
        with patch.dict(os.environ, {"HUNTX_ADMINS": "12345,9999"}):
            # Admins
            self.assertTrue(bot._is_admin("12345"))
            self.assertTrue(bot._is_admin("9999", "some_username"))
            
            # Non-admins
            self.assertFalse(bot._is_admin("11111"))
            self.assertFalse(bot._is_admin("22222", "regular_user"))
