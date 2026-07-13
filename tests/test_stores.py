import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from huntx.store.artifact_store import ArtifactStore
from huntx.store.raw_store import RawStore


class TestRawStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.store = RawStore(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_and_get(self):
        data = b"some raw data"
        artifact_hash = self.store.save(data)
        self.assertIsNotNone(artifact_hash)
        self.assertTrue(self.store.exists(artifact_hash))
        self.assertEqual(self.store.get(artifact_hash), data)

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get("nonexistent"))
        self.assertFalse(self.store.exists("nonexistent"))

    def test_prune_orphans(self):
        data1 = b"blob 1"
        hash1 = self.store.save(data1)
        data2 = b"blob 2"
        hash2 = self.store.save(data2)

        mock_repo = mock.MagicMock()
        mock_repo.get_all_known_hashes.return_value = {hash1}

        pruned = self.store.prune_orphans(mock_repo)

        self.assertEqual(pruned, 1)
        self.assertTrue(self.store.exists(hash1))
        self.assertFalse(self.store.exists(hash2))


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
        artifact_hash = self.store.save_artifact(route, fmt, data)
        self.assertIsNotNone(artifact_hash)

        loaded = self.store.get_artifact(route, artifact_hash, fmt)
        self.assertEqual(loaded, data)

    def test_save_artifact_does_not_rewrite_identical_content_addressed_file(self):
        artifact_hash = self.store.save_artifact("route1", "txt", b"processed data")
        target = self.store.internal_dir / "route1" / f"{artifact_hash}.txt"
        before = target.stat().st_mtime_ns

        with mock.patch("huntx.store.artifact_store.atomic_write") as writer:
            repeated_hash = self.store.save_artifact("route1", "txt", b"processed data")

        self.assertEqual(repeated_hash, artifact_hash)
        writer.assert_not_called()
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_save_output_user_facing(self):
        route = "route1"
        fmt = "txt"
        data = b"final output"
        path = self.store.save_output(route, fmt, data)
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), data)

    def test_unchanged_output_does_not_create_duplicate_archive(self):
        self.store.save_output("route1", "txt", b"final output")
        first_archives = list(self.store.archive_dir.iterdir())
        self.assertEqual(len(first_archives), 1)

        self.store.save_output("route1", "txt", b"final output")
        second_archives = list(self.store.archive_dir.iterdir())
        self.assertEqual(second_archives, first_archives)

    def test_changed_output_creates_new_archive(self):
        self.store.save_output("route1", "txt", b"first")
        self.store.save_output("route1", "txt", b"second")
        self.assertEqual(len(list(self.store.archive_dir.iterdir())), 2)

    def test_get_artifact_nonexistent(self):
        self.assertIsNone(self.store.get_artifact("r", "h", "f"))


if __name__ == "__main__":
    unittest.main()
