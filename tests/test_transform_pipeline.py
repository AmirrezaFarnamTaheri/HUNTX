import unittest
import json
from unittest.mock import Mock, patch, call
from huntx.pipeline.transform import TransformPipeline


class TestTransformPipeline(unittest.TestCase):
    def setUp(self):
        self.raw_store = Mock()
        self.state_repo = Mock()
        self.registry = Mock()
        self.source_configs = {"src1": Mock(selector=Mock(include_formats=["fmt1"]))}
        self.pipeline = TransformPipeline(self.raw_store, self.state_repo, self.registry, self.source_configs)

    def test_process_single_file_success(self):
        """_process_single_file should return record_rows and 'ok' status."""
        row = {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "file_size": 100}

        self.raw_store.get.return_value = b"config content"

        handler = Mock()
        handler.format_id = "fmt1"
        handler.parse.return_value = [{"unique_hash": "u1", "data": "parsed"}]
        self.registry.get.return_value = handler

        with patch("huntx.pipeline.transform.decide_format", return_value="fmt1"):
            result = self.pipeline._process_single_file(row)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["records"], 1)
        self.assertEqual(len(result["record_rows"]), 1)
        self.assertEqual(result["record_rows"][0][0], "hash123")  # raw_hash
        self.assertEqual(result["record_rows"][0][1], "fmt1")     # record_type
        self.assertEqual(result["status_update"], ("processed", None, "hash123"))
        self.raw_store.get.assert_called_with("hash123")
        handler.parse.assert_called_once()

    def test_process_single_file_missing_data(self):
        """Missing raw data should return failed status."""
        row = {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "file_size": 0}
        self.raw_store.get.return_value = None

        result = self.pipeline._process_single_file(row)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["status_update"], ("failed", "Raw data missing", "hash123"))

    def test_process_single_file_excluded_format(self):
        """Excluded format should return skipped status."""
        self.source_configs["src1"].selector.include_formats = ["other_fmt"]
        row = {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "file_size": 10}
        self.raw_store.get.return_value = b"data"

        with patch("huntx.pipeline.transform.decide_format", return_value="fmt1"):
            result = self.pipeline._process_single_file(row)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["status_update"], ("ignored", "Format fmt1 not allowed", "hash123"))

    def test_process_single_file_exception(self):
        """Store exception should return failed status."""
        row = {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "file_size": 0}
        self.raw_store.get.side_effect = Exception("Store error")

        result = self.pipeline._process_single_file(row)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["status_update"], ("failed", "Store error", "hash123"))

    def test_process_single_file_unknown_format(self):
        """Unknown format (no handler) should return failed status."""
        self.source_configs["src1"].selector.include_formats = ["unknown_fmt"]
        row = {"raw_hash": "hash123", "source_id": "src1", "filename": "test.conf", "file_size": 10}
        self.raw_store.get.return_value = b"data"
        self.registry.get.return_value = None

        with patch("huntx.pipeline.transform.decide_format", return_value="unknown_fmt"):
            result = self.pipeline._process_single_file(row)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["status_update"], ("failed", "No handler for unknown_fmt", "hash123"))

    def test_flush_batch(self):
        """_flush_batch should call batch DB methods with accumulated results."""
        results = [
            {
                "status": "ok",
                "record_rows": [("h1", "fmt1", "u1", '{"d":1}')],
                "status_update": ("processed", None, "h1"),
                "format": "fmt1",
            },
            {
                "status": "failed",
                "record_rows": [],
                "status_update": ("failed", "Raw data missing", "h2"),
                "format": None,
            },
            {
                "status": "skipped",
                "record_rows": [],
                "status_update": ("ignored", "Format x not allowed", "h3"),
                "format": "x",
            },
        ]

        records_inserted, processed, failed, skipped = self.pipeline._flush_batch(results)

        self.assertEqual(records_inserted, 1)
        self.assertEqual(processed, 1)
        self.assertEqual(failed, 1)
        self.assertEqual(skipped, 1)
        self.state_repo.add_records_batch.assert_called_once()
        self.state_repo.update_file_status_batch.assert_called_once()

    def test_process_pending_empty(self):
        """No pending files should exit early."""
        self.state_repo.get_pending_files.return_value = []
        self.pipeline.process_pending()
        self.state_repo.add_records_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
