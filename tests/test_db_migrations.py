import unittest
import sqlite3
import os
import tempfile
from pathlib import Path
from huntx.state.db import open_db


class TestDBMigrations(unittest.TestCase):
    def setUp(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.temp_db_file.name
        self.temp_db_file.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_migration_adds_metadata_json(self):
        # Create DB with old schema (missing metadata_json)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE seen_files ("
            "id INTEGER PRIMARY KEY, source_id TEXT, external_id TEXT, "
            "raw_hash TEXT, file_size INTEGER, filename TEXT, status TEXT, error_msg TEXT)"
        )
        conn.commit()
        conn.close()

        # Open DB via app logic, should trigger migration
        db = open_db(Path(self.db_path))

        # Verify column exists
        with db.connect() as conn:
            cursor = conn.execute("PRAGMA table_info(seen_files)")
            columns = [row["name"] for row in cursor.fetchall()]
            self.assertIn("metadata_json", columns)


if __name__ == "__main__":
    unittest.main()
