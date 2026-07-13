import tempfile
import unittest
from pathlib import Path

from huntx.state.db import DBConnection
from huntx.store.artifact_store import ArtifactStore
from huntx.utils.atomic import atomic_write_if_changed


class AtomicWriteOptimizationTests(unittest.TestCase):
    def test_atomic_write_if_changed_skips_identical_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value.bin"
            self.assertTrue(atomic_write_if_changed(path, b"same"))
            first_stat = path.stat()
            self.assertFalse(atomic_write_if_changed(path, b"same"))
            second_stat = path.stat()
            self.assertEqual(first_stat.st_ino, second_stat.st_ino)
            self.assertEqual(path.read_bytes(), b"same")

    def test_artifact_store_archives_only_changed_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(base_dir=Path(directory))
            store.save_output("route", "txt", b"one")
            store.save_output("route", "txt", b"one")
            self.assertEqual(len(list(store.archive_dir.iterdir())), 1)

            store.save_output("route", "txt", b"two")
            self.assertEqual(len(list(store.archive_dir.iterdir())), 2)


class SQLiteOptimizationTests(unittest.TestCase):
    def test_hot_query_indexes_and_connection_pragmas_are_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DBConnection(Path(directory) / "state.db")
            with database.connect() as connection:
                seen_indexes = {
                    row["name"] for row in connection.execute("PRAGMA index_list(seen_files)")
                }
                record_indexes = {
                    row["name"] for row in connection.execute("PRAGMA index_list(records)")
                }
                published_indexes = {
                    row["name"]
                    for row in connection.execute("PRAGMA index_list(published_artifacts)")
                }

                self.assertIn("idx_seen_files_pending", seen_indexes)
                self.assertIn("idx_seen_files_source_delta", seen_indexes)
                self.assertIn("idx_records_build", record_indexes)
                self.assertIn("idx_published_route_latest", published_indexes)
                self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA temp_store").fetchone()[0], 2)
                self.assertEqual(connection.execute("PRAGMA cache_size").fetchone()[0], -32768)


if __name__ == "__main__":
    unittest.main()
