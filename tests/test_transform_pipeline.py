import unittest
from unittest.mock import Mock, patch
from huntx.pipeline.transform import TransformPipeline


class TestTransformPipeline(unittest.TestCase):
    def setUp(self):
        self.raw_store = Mock()
        self.state_repo = Mock()
        self.registry = Mock()
        self.source_configs = {"src1": Mock(selector=Mock(include_formats=["fmt1"]))}
        self.pipeline = TransformPipeline(self.raw_store, self.state_repo, self.registry, self.source_configs)

    def test_process_pending_success(self):
        # Setup pending file
        self.state_repo.get_pending_files.return_value = [
            {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "metadata": {}}
        ]

        self.raw_store.get.return_value = b"config content"

        # Mock registry and handler
        handler = Mock()
        handler.format_id = "fmt1"
        handler.parse.return_value = [{"unique_hash": "u1", "data": "parsed"}]
        self.registry.get.return_value = handler

        # Run
        with patch("huntx.pipeline.transform.decide_format", return_value="fmt1"):
            self.pipeline.process_pending()

        # Verify
        self.raw_store.get.assert_called_with("hash123")
        handler.parse.assert_called_once()
        self.state_repo.add_record.assert_called_once()
        self.state_repo.update_file_status.assert_called_with("hash123", "processed")

    def test_process_pending_missing_data(self):
        self.state_repo.get_pending_files.return_value = [
            {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf"}
        ]
        self.raw_store.get.return_value = None

        self.pipeline.process_pending()

        self.state_repo.update_file_status.assert_called_with("hash123", "failed", "Raw data missing")

    def test_process_pending_excluded_format(self):
        # Config excludes fmt1
        self.source_configs["src1"].selector.include_formats = ["other_fmt"]

        self.state_repo.get_pending_files.return_value = [
            {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf"}
        ]
        self.raw_store.get.return_value = b"data"

        with patch("huntx.pipeline.transform.decide_format", return_value="fmt1"):
            self.pipeline.process_pending()

        # Updated expectation: ignored with specific message
        self.state_repo.update_file_status.assert_called_with("hash123", "ignored", "Format fmt1 not allowed")

    def test_process_exception_during_processing(self):
        self.state_repo.get_pending_files.return_value = [
            {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf"}
        ]
        # store raises exception
        self.raw_store.get.side_effect = Exception("Store error")

        self.pipeline.process_pending()

        self.state_repo.update_file_status.assert_called_with("hash123", "failed", "Store error")

    def test_process_unknown_format(self):
        self.state_repo.get_pending_files.return_value = [
            {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf"}
        ]
        self.raw_store.get.return_value = b"data"

        # Config must include unknown_fmt otherwise it fails early as excluded
        self.source_configs["src1"].selector.include_formats = ["unknown_fmt"]

        # Registry returns None for unknown format
        self.registry.get.return_value = None

        with patch("huntx.pipeline.transform.decide_format", return_value="unknown_fmt"):
            self.pipeline.process_pending()

        self.state_repo.update_file_status.assert_called_with("hash123", "failed", "No handler for unknown_fmt")


if __name__ == "__main__":
    unittest.main()
