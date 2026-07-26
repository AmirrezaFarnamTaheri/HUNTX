"""Regression test: build queries must not duplicate records.

``seen_files.raw_hash`` is not unique — the schema only enforces
``UNIQUE(source_id, external_id)`` — so identical content seen in several
allowed sources yields several ``seen_files`` rows. The build queries join
``records`` to ``seen_files`` on that hash, which fanned one record out into N
identical result rows and re-emitted it N times into the published artifact
(duplicate proxy lines and inflated counts).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from huntx.state.db import open_db
from huntx.state.repo import StateRepo

_HASH_A = "a" * 64
_HASH_B = "b" * 64


class TestBuildRecordFanout(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = open_db(self.tmp / "test.db")
        self.repo = StateRepo(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seen(self, source_id, external_id, raw_hash):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, status) "
                "VALUES (?, ?, ?, 'processed')",
                (source_id, external_id, raw_hash),
            )

    def _record(self, raw_hash, unique_hash, line, record_type="npvt"):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, "
                "data_json, is_active) VALUES (?, ?, ?, ?, 1)",
                (raw_hash, record_type, unique_hash, json.dumps({"line": line})),
            )

    def test_content_seen_in_two_sources_yields_one_record(self):
        # The exact production scenario: the same proxy config reposted in two
        # monitored channels.
        self._seen("src1", "e1", _HASH_A)
        self._seen("src2", "e2", _HASH_A)
        self._record(_HASH_A, "uh1", "vmess://X")

        rows = self.repo.get_records_for_build(["npvt"], ["src1", "src2"])

        self.assertEqual(len(rows), 1, f"record was duplicated: {rows}")

    def test_many_sources_sharing_content_still_yields_one_record(self):
        for i in range(5):
            self._seen(f"src{i}", f"e{i}", _HASH_A)
        self._record(_HASH_A, "uh1", "vmess://X")

        rows = self.repo.get_records_for_build(
            ["npvt"], [f"src{i}" for i in range(5)]
        )

        self.assertEqual(len(rows), 1, f"record fanned out across sources: {rows}")

    def test_distinct_records_are_all_preserved(self):
        # Guard against "fixing" duplication by over-collapsing real records.
        self._seen("src1", "e1", _HASH_A)
        self._seen("src2", "e2", _HASH_A)  # shared content
        self._seen("src1", "e3", _HASH_B)
        self._record(_HASH_A, "uh1", "vmess://X")
        self._record(_HASH_B, "uh2", "vmess://Y")

        rows = self.repo.get_records_for_build(["npvt"], ["src1", "src2"])

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(r["data"]["line"] for r in rows), ["vmess://X", "vmess://Y"]
        )

    def test_inactive_records_still_excluded(self):
        self._seen("src1", "e1", _HASH_A)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO records (source_file_hash, record_type, unique_hash, "
                "data_json, is_active) VALUES (?, 'npvt', 'uh1', ?, 0)",
                (_HASH_A, json.dumps({"line": "vmess://gone"})),
            )

        self.assertEqual(self.repo.get_records_for_build(["npvt"], ["src1"]), [])

    def test_source_filter_still_applied(self):
        self._seen("other", "e1", _HASH_A)
        self._record(_HASH_A, "uh1", "vmess://X")

        self.assertEqual(self.repo.get_records_for_build(["npvt"], ["src1"]), [])


if __name__ == "__main__":
    unittest.main()
