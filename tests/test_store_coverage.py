import unittest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from mergebot.store.raw_store import RawStore
from mergebot.store.artifact_store import ArtifactStore


class TestStoreCoverage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        # We pass base_dir explicitly, so no patching needed for constructor defaults if we use them

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_raw_store(self):
        store = RawStore(base_dir=self.base_dir)

        data = b"hello world"
        # Save
        hash_val = store.save(data)

        # Get
        retrieved = store.get(hash_val)
        self.assertEqual(retrieved, data)

        # Has
        self.assertTrue(store.exists(hash_val))
        self.assertFalse(store.exists("nonexistent"))

        # Get nonexistent
        self.assertIsNone(store.get("nonexistent"))

    def test_artifact_store(self):
        store = ArtifactStore(base_dir=self.base_dir)

        # Save artifact
        h = store.save_artifact("route1", "txt", b"content")
        self.assertIsNotNone(h)

        # Get artifact
        retrieved = store.get_artifact("route1", h, "txt")
        self.assertEqual(retrieved, b"content")

        # Get nonexistent
        self.assertIsNone(store.get_artifact("route1", "bad", "txt"))

        # Save output
        path = store.save_output("route1", "txt", b"out_content")
        self.assertTrue(Path(path).exists())

    def test_raw_store_exceptions(self):
        store = RawStore(base_dir=self.base_dir)

        # Mock mkdir to raise exception
        with patch("pathlib.Path.mkdir", side_effect=Exception("Disk full")):
            with self.assertRaises(Exception):
                store.save(b"data")

        # To test get() exception we need a file that exists but fails on read
        # Create a file
        h = store.save(b"data")

        with patch("pathlib.Path.read_bytes", side_effect=Exception("IO Error")):
            # Store uses Path object methods
            store.get(h)
            # Actually get() catches exception and logs it, returns None
            self.assertIsNone(store.get(h))

    def test_artifact_store_exceptions(self):
        store = ArtifactStore(base_dir=self.base_dir)

        with patch("pathlib.Path.mkdir", side_effect=Exception("Disk full")):
            with self.assertRaises(Exception):
                store.save_artifact("r", "fmt", b"data")

        with patch("builtins.open", side_effect=Exception("Write fail")):
            with self.assertRaises(Exception):
                store.save_output("r", "fmt", b"data")


if __name__ == "__main__":
    unittest.main()
