"""Regression test: prune must not delete raw blobs still referenced by an
active blob-dependent record.

Reproduces the divergent-timeline data-loss scenario: a file ingested more
than N days ago (old ``seen_files.ingested_at``) whose still-active blob-
dependent record was created recently. Pruning by age must retain that blob
and its tracking row.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


class TestPruneBlobSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = open_db(self.tmp / "test.db")
        self.repo = StateRepo(self.db)
        # Pick a real blob-dependent format from the repo's own list.
        self.blob_format = list(self.repo._BLOB_DEPENDENT_FORMATS)[0]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _insert_seen_file(self, source_id, external_id, raw_hash, ingested_at, status="processed"):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, ingested_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_id, external_id, raw_hash, ingested_at, status),
            )

    def _insert_record(self, raw_hash, record_type, is_active, created_at):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, data_json, "
                "created_at, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                (raw_hash, record_type, f"uh-{raw_hash}", "{}", created_at, is_active),
            )

    def test_active_referenced_blob_is_retained(self):
        referenced = "a" * 64
        # Old ingest, but a fresh, active blob-dependent record references it.
        self._insert_seen_file("src", "ext1", referenced, "2000-01-01 00:00:00")
        self._insert_record(referenced, self.blob_format, is_active=1, created_at="2999-01-01 00:00:00")

        res = self.repo.prune_old_data(days=30)

        self.assertNotIn(referenced, res["raw_hashes"], "live-referenced blob must not be pruned")
        # The tracking row must survive so orphan-pruning can't delete it later.
        self.assertIn(referenced, self.repo.get_all_known_hashes())

    def test_unreferenced_old_blob_is_pruned(self):
        orphan = "b" * 64
        self._insert_seen_file("src", "ext2", orphan, "2000-01-01 00:00:00")
        # No active record references it.

        res = self.repo.prune_old_data(days=30)

        self.assertIn(orphan, res["raw_hashes"], "unreferenced old blob should be pruned")
        self.assertNotIn(orphan, self.repo.get_all_known_hashes())

    def test_inactive_record_does_not_protect_blob(self):
        stale = "c" * 64
        self._insert_seen_file("src", "ext3", stale, "2000-01-01 00:00:00")
        self._insert_record(stale, self.blob_format, is_active=0, created_at="2000-01-01 00:00:00")

        res = self.repo.prune_old_data(days=30)

        self.assertIn(stale, res["raw_hashes"], "blob referenced only by inactive record is prunable")


if __name__ == "__main__":
    unittest.main()
