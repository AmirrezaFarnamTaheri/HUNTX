"""Regression tests for store-layer hardening.

Covers two defects surfaced in the repository audit:

1. ``RejectsStore`` captured its base directory at import time, so
   ``paths.set_paths()`` reconfiguration was ignored and rejects were written
   to the wrong location.
2. ``RawStore.get``/``exists`` built filesystem paths directly from a caller
   supplied ``sha256`` without validating it, allowing a crafted value to
   escape ``base_dir``.
"""

import tempfile
import unittest
from pathlib import Path

from huntx.store import paths
from huntx.store.raw_store import RawStore
from huntx.store.rejects import RejectsStore


class TestRejectsStorePathBinding(unittest.TestCase):
    def test_default_dir_follows_runtime_reconfiguration(self):
        original = paths.REJECTS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            reconfigured = Path(tmp) / "rejects"
            try:
                paths.REJECTS_DIR = reconfigured
                store = RejectsStore()  # no explicit base_dir
                self.assertEqual(store.base_dir, reconfigured)
                store.save_reject("src1", "bad_format", b"payload")
                written = list(reconfigured.glob("*.dat"))
                self.assertEqual(len(written), 1)
                self.assertEqual(written[0].read_bytes(), b"payload")
            finally:
                paths.REJECTS_DIR = original


class TestRawStoreHashValidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RawStore(base_dir=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip_with_valid_hash(self):
        digest = self.store.save(b"hello world")
        self.assertTrue(self.store.exists(digest))
        self.assertEqual(self.store.get(digest), b"hello world")

    def test_traversal_hash_is_rejected(self):
        for evil in ("../../../etc/passwd", "..", "not-hex", "AB" * 32, "abc"):
            self.assertFalse(self.store.exists(evil), f"exists() accepted {evil!r}")
            self.assertIsNone(self.store.get(evil), f"get() accepted {evil!r}")

    def test_uppercase_hex_is_rejected(self):
        # Digests are produced lowercase; an uppercase variant is not a value
        # this store ever writes and must not be trusted for path building.
        digest = self.store.save(b"data")
        self.assertFalse(self.store.exists(digest.upper()))


if __name__ == "__main__":
    unittest.main()
