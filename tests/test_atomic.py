import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huntx.utils.atomic import atomic_write, atomic_write_if_changed


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir) / "test_file.txt"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_atomic_write_bytes(self):
        data = b"hello world"
        atomic_write(self.test_path, data)
        self.assertTrue(self.test_path.exists())
        self.assertEqual(self.test_path.read_bytes(), data)

    def test_atomic_write_str(self):
        data = "hello world"
        atomic_write(self.test_path, data)
        self.assertTrue(self.test_path.exists())
        self.assertEqual(self.test_path.read_text(), data)

    def test_overwrite(self):
        atomic_write(self.test_path, b"initial")
        atomic_write(self.test_path, b"updated")
        self.assertEqual(self.test_path.read_bytes(), b"updated")

    def test_directory_creation(self):
        nested_path = Path(self.test_dir) / "nested" / "file.txt"
        atomic_write(nested_path, b"data")
        self.assertTrue(nested_path.exists())

    def test_atomic_write_if_changed_skips_identical_payload(self):
        atomic_write(self.test_path, b"stable")
        before = self.test_path.stat().st_mtime_ns

        with patch("huntx.utils.atomic.os.replace") as replace:
            changed = atomic_write_if_changed(self.test_path, b"stable")

        self.assertFalse(changed)
        replace.assert_not_called()
        self.assertEqual(self.test_path.stat().st_mtime_ns, before)

    def test_atomic_write_if_changed_replaces_different_payload(self):
        atomic_write(self.test_path, b"old")
        changed = atomic_write_if_changed(self.test_path, b"new")
        self.assertTrue(changed)
        self.assertEqual(self.test_path.read_bytes(), b"new")

    def test_atomic_write_if_changed_handles_large_payload(self):
        payload = os.urandom((1024 * 1024) + 17)
        self.assertTrue(atomic_write_if_changed(self.test_path, payload))
        self.assertFalse(atomic_write_if_changed(self.test_path, payload))
        self.assertEqual(self.test_path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
