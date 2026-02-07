import unittest
from unittest.mock import Mock, patch, MagicMock
from mergebot.pipeline.ingest import IngestionPipeline

class TestIngestPipeline(unittest.TestCase):
    def setUp(self):
        self.raw_store = Mock()
        self.state_repo = Mock()

        # Mock the db.connect context manager
        # When db.connect() is called, it returns a context manager.
        # The context manager's __enter__ returns the connection object.
        self.mock_conn = MagicMock()

        # Create a mock for the context manager
        self.mock_ctx_mgr = MagicMock()
        self.mock_ctx_mgr.__enter__.return_value = self.mock_conn
        self.mock_ctx_mgr.__exit__.return_value = None

        # Assign it to db.connect return value
        self.state_repo.db.connect.return_value = self.mock_ctx_mgr

        self.pipeline = IngestionPipeline(self.raw_store, self.state_repo)
        self.connector = Mock()

    def test_ingest_new_files(self):
        # Setup mocks
        self.state_repo.get_source_state.return_value = {}
        self.state_repo.has_seen_file.return_value = False

        item = Mock()
        item.external_id = "123"
        item.data = b"test data"
        item.metadata = {"filename": "test.txt"}

        self.connector.list_new.return_value = [item]
        self.connector.get_state.return_value = {"offset": 100}

        self.raw_store.save.return_value = "hash123"

        # Run
        self.pipeline.run("source1", self.connector)

        # Verify
        self.raw_store.save.assert_called_with(b"test data")

        # record_file should be called with conn argument
        self.state_repo.record_file.assert_called_once()
        args, kwargs = self.state_repo.record_file.call_args
        self.assertEqual(kwargs['conn'], self.mock_conn)

        # update_source_state called with conn
        self.state_repo.update_source_state.assert_called_once()
        args, kwargs = self.state_repo.update_source_state.call_args
        self.assertEqual(kwargs['conn'], self.mock_conn)

    def test_skip_seen_files(self):
        self.state_repo.get_source_state.return_value = {}
        self.state_repo.has_seen_file.return_value = True

        item = Mock()
        item.external_id = "123"

        self.connector.list_new.return_value = [item]
        self.connector.get_state.return_value = {"offset": 100}

        self.pipeline.run("source1", self.connector)

        self.raw_store.save.assert_not_called()
        self.state_repo.record_file.assert_not_called()

if __name__ == '__main__':
    unittest.main()
