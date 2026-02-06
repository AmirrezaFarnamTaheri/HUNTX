import unittest
from unittest.mock import Mock, MagicMock, patch
from mergebot.pipeline.transform import TransformPipeline

class TestTransformPipeline(unittest.TestCase):
    def setUp(self):
        self.raw_store = Mock()
        self.state_repo = Mock()
        self.registry = Mock()
        self.pipeline = TransformPipeline(self.raw_store, self.state_repo, self.registry)

    def test_process_pending_success(self):
        # Setup pending file
        self.state_repo.get_pending_files.return_value = [{
            "raw_hash": "hash123",
            "source_id": "src1",
            "filename": "test.conf"
        }]

        self.raw_store.get.return_value = b"config content"

        # Mock registry and handler
        handler = Mock()
        handler.parse.return_value = [{"unique_hash": "u1", "data": "parsed"}]
        self.registry.get.return_value = handler

        # Run
        with patch("mergebot.pipeline.transform.decide_format", return_value="fmt1"):
            self.pipeline.process_pending()

        # Verify
        self.raw_store.get.assert_called_with("hash123")
        handler.parse.assert_called_once()
        self.state_repo.add_record.assert_called_once()
        self.state_repo.update_file_status.assert_called_with("hash123", "processed")

    def test_process_pending_missing_data(self):
        self.state_repo.get_pending_files.return_value = [{
            "raw_hash": "hash123",
            "source_id": "src1",
            "filename": "test.conf"
        }]
        self.raw_store.get.return_value = None

        self.pipeline.process_pending()

        self.state_repo.update_file_status.assert_called_with("hash123", "failed", "Raw data missing")

if __name__ == '__main__':
    unittest.main()
