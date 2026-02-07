import unittest
import sqlite3
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from mergebot.state.db import open_db
from mergebot.state.repo import StateRepo

class TestDBStateCoverage(unittest.TestCase):
    def setUp(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.temp_db_file.name
        self.temp_db_file.close()
        self.db = open_db(Path(self.db_path))
        self.repo = StateRepo(self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_open_db_creates_schema(self):
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_state';")
            self.assertIsNotNone(cursor.fetchone())
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seen_files';")
            self.assertIsNotNone(cursor.fetchone())

    def test_update_source_state_bot(self):
        source_id = "bot_src"
        state = {"offset": 100}
        self.repo.update_source_state(source_id, state, source_type="telegram")

        fetched = self.repo.get_source_state(source_id)
        self.assertEqual(fetched, state)

    def test_record_file_duplicates(self):
        self.repo.record_file("src1", "ext1", "hash1", 100, "f1.txt", "pending", {})
        self.repo.record_file("src1", "ext1", "hash2", 200, "f1_v2.txt", "processed", {"foo": "bar"})

        with self.db.connect() as conn:
            cursor = conn.execute("SELECT raw_hash, file_size, filename, status FROM seen_files WHERE external_id=?", ("ext1",))
            row = cursor.fetchone()
            self.assertEqual(row[0], "hash1")
            self.assertEqual(row[1], 100)
            self.assertEqual(row[3], "pending")

    def test_get_pending_files(self):
        self.repo.record_file("src1", "ext1", "h1", 10, "f1", "pending", {})
        self.repo.record_file("src1", "ext2", "h2", 20, "f2", "transformed", {})
        self.repo.record_file("src1", "ext3", "h3", 30, "f3", "pending", {})

        pending = list(self.repo.get_pending_files())
        self.assertEqual(len(pending), 2)
        ids = [p['external_id'] for p in pending]
        self.assertIn("ext1", ids)
        self.assertIn("ext3", ids)

    def test_update_file_status(self):
        self.repo.record_file("src1", "ext1", "h1", 10, "f1", "pending", {})
        self.repo.update_file_status("h1", "transformed")

        with self.db.connect() as conn:
            cursor = conn.execute("SELECT status FROM seen_files WHERE external_id=?", ("ext1",))
            row = cursor.fetchone()
            self.assertEqual(row[0], "transformed")

    def test_has_seen_file(self):
        self.assertFalse(self.repo.has_seen_file("src1", "ext1"))
        self.repo.record_file("src1", "ext1", "h1", 10, "f1", "pending", {})
        self.assertTrue(self.repo.has_seen_file("src1", "ext1"))

    def test_get_records_for_build(self):
        self.repo.record_file("src1", "ext1", "h1", 10, "f1", "transformed", {})
        self.repo.add_record("h1", "fmt1", "unique1", {"data": "foo"})

        records = self.repo.get_records_for_build(["fmt1"], ["src1"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["data"], "foo")

        records = self.repo.get_records_for_build(["fmt1"], ["src2"])
        self.assertEqual(len(records), 0)

    def test_publish_artifacts(self):
        route = "r1"
        h = "hash123"
        self.assertFalse(self.repo.is_artifact_published(route, h))
        self.assertIsNone(self.repo.get_last_published_hash(route))

        self.repo.mark_published(route, h, {"meta": 1})

        self.assertTrue(self.repo.is_artifact_published(route, h))
        self.assertEqual(self.repo.get_last_published_hash(route), h)

    def test_repo_exceptions(self):
        # We need to mock connect() to raise exception when called
        # DBConnection.connect() is a context manager.
        original_connect = self.db.connect

        mock_connect = MagicMock()
        mock_connect.__enter__.side_effect = Exception("DB Error")
        self.db.connect = MagicMock(return_value=mock_connect)

        self.assertIsNone(self.repo.get_source_state("id"))

        # update_source_state raises exception
        with self.assertRaises(Exception):
             self.repo.update_source_state("id", {})

        self.assertFalse(self.repo.has_seen_file("id", "ext"))
        self.repo.record_file("id", "ext", "hash", 1, "f")
        self.repo.update_file_status("hash", "stat")
        self.assertEqual(self.repo.get_pending_files(), [])
        self.repo.add_record("hash", "type", "uniq", {})
        self.assertEqual(self.repo.get_records_for_build(["t"], ["s"]), [])
        self.assertFalse(self.repo.is_artifact_published("r", "h"))
        self.repo.mark_published("r", "h")
        self.assertIsNone(self.repo.get_last_published_hash("r"))

        self.db.connect = original_connect

if __name__ == '__main__':
    unittest.main()
