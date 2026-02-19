import unittest
from unittest.mock import Mock, MagicMock
from huntx.pipeline.ingest import IngestionPipeline

class TestIngestPipeline(unittest.TestCase):
    def setUp(self):
        self.raw_store = Mock()
        self.state_repo = Mock()

        # Mock db connection context manager
        self.mock_conn = MagicMock()
        self.mock_ctx_mgr = MagicMock()
        self.mock_ctx_mgr.__enter__.return_value = self.mock_conn
        self.mock_ctx_mgr.__exit__.return_value = None
        self.state_repo.db.connect.return_value = self.mock_ctx_mgr

        self.pipeline = IngestionPipeline(self.raw_store, self.state_repo)
        self.connector = Mock()

    def test_ingest_new_files(self):
        # Setup mocks
        self.state_repo.get_source_state.return_value = {}
        # has_seen_file is replaced by batch check
        self.state_repo.get_seen_files_batch.return_value = set()

        item = Mock()
        item.external_id = "123"
        item.data = b"test data"
        item.metadata = {"filename": "test.txt", "is_text": True}

        self.connector.list_new.return_value = [item]
        self.connector.get_state.return_value = {"offset": 100}

        self.raw_store.save.return_value = "hash123"

        # Run
        self.pipeline.run("source1", self.connector)

        # Verify
        self.raw_store.save.assert_called_with(b"test data")

        # Verify batch methods
        self.state_repo.get_seen_files_batch.assert_called_once()
        self.state_repo.record_files_batch.assert_called_once()

        # Check arguments for record_files_batch
        args, kwargs = self.state_repo.record_files_batch.call_args
        records = args[0]
        self.assertEqual(len(records), 1)
        # Record tuple: (source_id, external_id, raw_hash, file_size, filename, status, metadata_json)
        self.assertEqual(records[0][0], "source1")
        self.assertEqual(records[0][1], "123")
        self.assertEqual(records[0][2], "hash123")

        self.assertEqual(kwargs["conn"], self.mock_conn)

        # update_source_state called with conn
        self.state_repo.update_source_state.assert_called_once()

    def test_skip_seen_files(self):
        self.state_repo.get_source_state.return_value = {}
        # Return ID as seen
        self.state_repo.get_seen_files_batch.return_value = {"123"}

        item = Mock()
        item.external_id = "123"

        self.connector.list_new.return_value = [item]
        self.connector.get_state.return_value = {"offset": 100}

        self.pipeline.run("source1", self.connector)

        self.raw_store.save.assert_not_called()
        self.state_repo.record_files_batch.assert_not_called()

if __name__ == "__main__":
    unittest.main()
