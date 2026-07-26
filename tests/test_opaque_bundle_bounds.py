"""Tests for the bounded-resource ceilings in ``OpaqueBundleHandler.build``.

Normal-size bundles must be unaffected; pathological record sets must be capped
by byte and entry ceilings, with the drop surfaced (never silent).
"""

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from huntx.formats.opaque_bundle import OpaqueBundleHandler
from huntx.store.raw_store import RawStore


def _records_for(store, blobs):
    """Persist blobs and return matching opaque_bundle records."""
    records = []
    for name, payload in blobs:
        digest = store.save(payload)
        records.append({"data": {"filename": name, "blob_hash": digest, "size": len(payload)}})
    return records


class TestOpaqueBundleBounds(unittest.TestCase):
    _LIMIT_VARS = ("HUNTX_OPAQUE_BUNDLE_MAX_BYTES", "HUNTX_OPAQUE_BUNDLE_MAX_ENTRIES")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RawStore(base_dir=Path(self._tmp.name))
        self.handler = OpaqueBundleHandler(self.store)
        # Save and clear so tests run against known defaults, then restore
        # whatever was actually present (or absent) — an unconditional pop in
        # tearDown would erase a value CI or another test had configured.
        self._saved_env = {var: os.environ[var] for var in self._LIMIT_VARS if var in os.environ}
        for var in self._LIMIT_VARS:
            os.environ.pop(var, None)

    def tearDown(self):
        for var in self._LIMIT_VARS:
            os.environ.pop(var, None)
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    def _names_in(self, blob):
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            return set(zf.namelist())

    def test_normal_bundle_includes_all_entries(self):
        records = _records_for(self.store, [("a.txt", b"aaa"), ("b.txt", b"bbb")])
        names = self._names_in(self.handler.build(records))
        self.assertEqual(names, {"a.txt", "b.txt"})

    def test_byte_ceiling_truncates(self):
        os.environ["HUNTX_OPAQUE_BUNDLE_MAX_BYTES"] = "10"
        records = _records_for(
            self.store,
            [("a.txt", b"x" * 8), ("b.txt", b"y" * 8), ("c.txt", b"z" * 8)],
        )
        names = self._names_in(self.handler.build(records))
        # Only the first entry (8 bytes) fits under a 10-byte ceiling.
        self.assertEqual(names, {"a.txt"})

    def test_entry_ceiling_truncates(self):
        os.environ["HUNTX_OPAQUE_BUNDLE_MAX_ENTRIES"] = "2"
        records = _records_for(
            self.store,
            [("a.txt", b"a"), ("b.txt", b"b"), ("c.txt", b"c"), ("d.txt", b"d")],
        )
        names = self._names_in(self.handler.build(records))
        self.assertEqual(len(names), 2)

    def test_invalid_env_falls_back_to_default(self):
        os.environ["HUNTX_OPAQUE_BUNDLE_MAX_BYTES"] = "not-a-number"
        records = _records_for(self.store, [("a.txt", b"aaa")])
        names = self._names_in(self.handler.build(records))
        self.assertEqual(names, {"a.txt"})

    def test_missing_blob_is_skipped_not_fatal(self):
        records = [
            {"data": {"filename": "ghost.txt", "blob_hash": "0" * 64, "size": 3}},
            *_records_for(self.store, [("real.txt", b"real")]),
        ]
        names = self._names_in(self.handler.build(records))
        self.assertEqual(names, {"real.txt"})


if __name__ == "__main__":
    unittest.main()
