import unittest
import shutil
import tempfile
import os
from pathlib import Path
from mergebot.store.raw_store import RawStore
from mergebot.store.artifact_store import ArtifactStore

class TestStoreCoverage(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_raw_store(self):
        base_dir = Path(self.test_dir) / "raw"
        store = RawStore(base_dir=base_dir)

        data = b"hello world"
        hash_val = store.save(data)

        self.assertTrue(store.exists(hash_val))
        self.assertEqual(store.get(hash_val), data)
        self.assertIsNone(store.get("nonexistent"))

    def test_artifact_store(self):
        base_dir = Path(self.test_dir) / "artifacts"
        # Mock DATA_DIR used inside ArtifactStore
        with unittest.mock.patch('mergebot.store.artifact_store.DATA_DIR', Path(self.test_dir) / "data"):
            store = ArtifactStore(base_dir=base_dir)

            sha = store.save_artifact("route1", b"content")
            self.assertIsNotNone(store.get_artifact("route1", sha))
            self.assertEqual(store.get_artifact("route1", sha), b"content")

            out_path = store.save_output("route1", "txt", b"output_content")
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, "rb") as f:
                self.assertEqual(f.read(), b"output_content")

            self.assertIsNone(store.get_artifact("route1", "badhash"))

    def test_raw_store_exceptions(self):
        base_dir = Path(self.test_dir) / "raw_err"
        store = RawStore(base_dir=base_dir)

        with unittest.mock.patch.object(Path, 'mkdir', side_effect=Exception("Disk full")):
            with self.assertRaises(Exception):
                store.save(b"data")

        with unittest.mock.patch.object(Path, 'read_bytes', side_effect=Exception("IO Error")):
             h = "hash"
             p = base_dir / h[:2] / h
             p.parent.mkdir(parents=True, exist_ok=True)
             with open(p, "wb") as f: f.write(b"")

             self.assertIsNone(store.get(h))

    def test_artifact_store_exceptions(self):
        base_dir = Path(self.test_dir) / "art_err"
        with unittest.mock.patch('mergebot.store.artifact_store.DATA_DIR', Path(self.test_dir) / "data"):
             store = ArtifactStore(base_dir=base_dir)

             with unittest.mock.patch.object(Path, 'mkdir', side_effect=Exception("Disk full")):
                 with self.assertRaises(Exception):
                     store.save_artifact("n", b"d")

             with unittest.mock.patch('builtins.open', side_effect=Exception("Write fail")):
                 with self.assertRaises(Exception):
                     store.save_output("n", "fmt", b"d")

if __name__ == '__main__':
    unittest.main()
