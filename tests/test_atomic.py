import unittest
import tempfile
import os
from pathlib import Path
from src.mergebot.utils.atomic import atomic_write

class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir) / "test_file.txt"

    def tearDown(self):
        import shutil
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

if __name__ == "__main__":
    unittest.main()
