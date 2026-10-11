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


def test_vmess_identity_migration_ignores_legacy_fragment():
    """A legacy # name must not stop VMess re-keying or leak into its identity."""
    import base64
    import hashlib
    import json

    from huntx.state.db import _canonicalize_vmess_line

    payload = {"port": "443", "add": "node.example.com", "ps": "legacy"}
    source = "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode()
    canonical = _canonicalize_vmess_line(source + "#old-fragment")
    expected_payload = {"add": "node.example.com", "port": "443"}
    expected = "vmess://" + base64.b64encode(
        json.dumps(expected_payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    assert canonical == expected
    assert hashlib.sha256(canonical.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
