import unittest
import shutil
import tempfile
import os
from pathlib import Path
from huntx.store.raw_store import RawStore
from huntx.store.artifact_store import ArtifactStore


class TestRawStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.store = RawStore(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_and_get(self):
        data = b"some raw data"
        h = self.store.save(data)
        self.assertIsNotNone(h)
        self.assertTrue(self.store.exists(h))
        self.assertEqual(self.store.get(h), data)

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get("nonexistent"))
        self.assertFalse(self.store.exists("nonexistent"))


class TestArtifactStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.store = ArtifactStore(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_artifact_internal(self):
        route = "route1"
        fmt = "txt"
        data = b"processed data"
        h = self.store.save_artifact(route, fmt, data)
        self.assertIsNotNone(h)

        loaded = self.store.get_artifact(route, h, fmt)
        self.assertEqual(loaded, data)

    def test_save_output_user_facing(self):
        route = "route1"
        fmt = "txt"
        data = b"final output"
        path = self.store.save_output(route, fmt, data)
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_get_artifact_nonexistent(self):
        self.assertIsNone(self.store.get_artifact("r", "h", "f"))


if __name__ == "__main__":
    unittest.main()
