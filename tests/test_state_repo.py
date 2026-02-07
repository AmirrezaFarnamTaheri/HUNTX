import unittest
import sqlite3
import json
import logging
from unittest.mock import MagicMock
from mergebot.state.repo import StateRepo
from mergebot.state.db import DBConnection

class TestStateRepo(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite for testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        # Apply schema manually since DBConnection usually does it from file
        self.conn.executescript("""
        CREATE TABLE source_state (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            state_json TEXT,
            updated_at INTEGER
        );
        CREATE TABLE seen_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            external_id TEXT NOT NULL,
            raw_hash TEXT NOT NULL,
            file_size INTEGER,
            filename TEXT,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            metadata_json TEXT,
            first_seen_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_id, external_id)
        );
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_hash TEXT NOT NULL,
            record_type TEXT NOT NULL,
            unique_hash TEXT NOT NULL,
            data_json TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE published_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_name TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            metadata_json TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Mock DBConnection to return our memory connection
        # StateRepo calls db.connect() which returns a context manager yielding the connection
        self.mock_db_conn = MagicMock()
        self.mock_db_conn.connect.return_value.__enter__.return_value = self.conn
        self.mock_db_conn.connect.return_value.__exit__.return_value = None

        self.repo = StateRepo(self.mock_db_conn)

        # Suppress logging during tests
        logging.getLogger('mergebot.state.repo').setLevel(logging.CRITICAL)

    def tearDown(self):
        self.conn.close()

    def test_source_state_update_and_retrieve(self):
        # Test initial get (should be None)
        self.assertIsNone(self.repo.get_source_state("src1"))

        # Test update
        state = {"offset": 100}
        self.repo.update_source_state("src1", state)

        # Test get after update
        retrieved = self.repo.get_source_state("src1")
        self.assertEqual(retrieved, state)

    def test_record_file_persistence(self):
        source_id = "src1"
        ext_id = "101"

        self.assertFalse(self.repo.has_seen_file(source_id, ext_id))

        self.repo.record_file(source_id, ext_id, "hash1", 100, "file.txt")

        self.assertTrue(self.repo.has_seen_file(source_id, ext_id))

        # Check pending files
        pending = self.repo.get_pending_files()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["filename"], "file.txt")

        # Check status update
        self.repo.update_file_status("hash1", "processed")
        pending_after = self.repo.get_pending_files()
        self.assertEqual(len(pending_after), 0)

    def test_add_record_and_build_query(self):
        # Insert a file first (needed for JOIN in get_records_for_build)
        self.repo.record_file("src1", "101", "rawhash1", 100, "file.txt")

        # Add a record linked to that file
        record_data = {"key": "val"}
        self.repo.add_record("rawhash1", "fmt1", "unique1", record_data)

        # Test fetch
        records = self.repo.get_records_for_build(["fmt1"], ["src1"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], record_data)

        # Test filter by source (should return empty)
        records_wrong_source = self.repo.get_records_for_build(["fmt1"], ["src2"])
        self.assertEqual(len(records_wrong_source), 0)

        # Test filter by type (should return empty)
        records_wrong_type = self.repo.get_records_for_build(["fmt2"], ["src1"])
        self.assertEqual(len(records_wrong_type), 0)

    def test_published_artifacts_tracking(self):
        route = "route1"
        h = "art_hash_1"

        self.assertIsNone(self.repo.get_last_published_hash(route))

        self.repo.mark_published(route, h)

        self.assertEqual(self.repo.get_last_published_hash(route), h)
        self.assertTrue(self.repo.is_artifact_published(route, h))

if __name__ == '__main__':
    unittest.main()
