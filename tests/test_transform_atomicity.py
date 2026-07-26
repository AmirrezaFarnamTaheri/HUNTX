"""Regression test: record inserts and status flips must be one transaction.

``add_records_batch`` and ``update_file_status_batch`` previously each opened
their own connection, so they committed independently. A crash (or an exception
in the second call) after records committed but before the source files left
``'pending'`` meant the next run re-fetched those files, re-parsed them, and
inserted the same records again under new ids — unbounded ``records`` growth and
the transform stage repeating that work forever. Build-time dedup masked the
output impact, which is exactly why this needs a test at the storage layer.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from huntx.state.db import open_db
from huntx.state.repo import StateRepo

_HASH = "c" * 64


class TestTransformFlushAtomicity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = open_db(self.tmp / "test.db")
        self.repo = StateRepo(self.db)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, status) "
                "VALUES ('s1', 'e1', ?, 'pending')",
                (_HASH,),
            )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _counts(self):
        with self.db.connect() as conn:
            records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            status = conn.execute(
                "SELECT status FROM seen_files WHERE raw_hash = ?", (_HASH,)
            ).fetchone()[0]
        return records, status

    def test_both_writes_commit_together(self):
        rows = [(_HASH, "npvt", "uh1", json.dumps({"line": "vmess://X"}))]
        updates = [("processed", None, _HASH)]

        with self.db.connect() as conn:
            self.repo.add_records_batch(rows, conn=conn)
            self.repo.update_file_status_batch(updates, conn=conn)

        self.assertEqual(self._counts(), (1, "processed"))

    def test_failure_after_insert_rolls_back_the_records(self):
        # The exact interleaving that used to strand data: records inserted,
        # then the transaction fails before the status flip.
        rows = [(_HASH, "npvt", "uh1", json.dumps({"line": "vmess://X"}))]

        with self.assertRaises(RuntimeError):
            with self.db.connect() as conn:
                self.repo.add_records_batch(rows, conn=conn)
                raise RuntimeError("simulated crash before status update")

        records, status = self._counts()
        self.assertEqual(records, 0, "records survived a rolled-back transaction")
        self.assertEqual(status, "pending", "file status changed despite rollback")

    def test_failure_after_status_update_rolls_back_the_status(self):
        updates = [("processed", None, _HASH)]

        with self.assertRaises(RuntimeError):
            with self.db.connect() as conn:
                self.repo.update_file_status_batch(updates, conn=conn)
                raise RuntimeError("simulated crash after status update")

        _, status = self._counts()
        self.assertEqual(status, "pending")

    def test_standalone_calls_still_work_without_conn(self):
        # Other callers pass no connection and must keep self-committing.
        self.repo.add_records_batch(
            [(_HASH, "npvt", "uh2", json.dumps({"line": "vmess://Y"}))]
        )
        self.repo.update_file_status_batch([("processed", None, _HASH)])
        self.assertEqual(self._counts(), (1, "processed"))


if __name__ == "__main__":
    unittest.main()
