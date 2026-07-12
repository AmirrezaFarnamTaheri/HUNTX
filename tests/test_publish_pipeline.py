import unittest
from unittest.mock import Mock, patch

from huntx.pipeline.publish import PublishPipeline


class TestPublishPipeline(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.pipeline = PublishPipeline(self.state_repo)

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_publish_new_content(self, MockPublisher):
        build_result = {"route_name": "route1", "artifact_hash": "new_hash", "format": "fmt1", "data": b"data"}
        destinations = [{"chat_id": "123", "token": "test-value"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"
        mock_pub_instance = Mock()
        MockPublisher.return_value = mock_pub_instance

        self.pipeline.run(build_result, destinations)

        mock_pub_instance.publish.assert_called_once()
        self.state_repo.mark_published.assert_called_with("route1", "new_hash")

    def test_skip_same_content(self):
        build_result = {"route_name": "route1", "artifact_hash": "same_hash", "format": "fmt1"}
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "same_hash"

        with patch("huntx.pipeline.publish.TelegramPublisher") as MockPublisher:
            self.pipeline.run(build_result, destinations)
            MockPublisher.assert_not_called()

    @patch.dict("os.environ", {"CI": "0", "HUNTX_STRICT": "0"}, clear=False)
    def test_skip_when_destination_has_no_token(self):
        build_result = {"route_name": "route1", "artifact_hash": "new_hash", "format": "fmt1", "data": b"x"}
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        result = self.pipeline.run(build_result, destinations)

        self.assertTrue(result)
        self.state_repo.mark_published.assert_not_called()

    @patch.dict("os.environ", {"CI": "1", "HUNTX_STRICT": "0"}, clear=False)
    def test_missing_destination_token_raises_in_ci(self):
        build_result = {"route_name": "route1", "artifact_hash": "new_hash", "format": "fmt1", "data": b"x"}
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        with self.assertRaisesRegex(RuntimeError, "Strict Mode Active"):
            self.pipeline.run(build_result, destinations)

        self.state_repo.mark_published.assert_not_called()


if __name__ == "__main__":
    unittest.main()
