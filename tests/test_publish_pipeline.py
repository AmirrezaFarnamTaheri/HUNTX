import unittest
from unittest.mock import Mock, patch
from mergebot.pipeline.publish import PublishPipeline

class TestPublishPipeline(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.pipeline = PublishPipeline(self.state_repo)

    @patch("mergebot.pipeline.publish.TelegramPublisher")
    def test_publish_new_content(self, MockPublisher):
        # Setup
        build_result = {
            "route_name": "route1",
            "artifact_hash": "new_hash",
            "format": "fmt1",
            "data": b"data"
        }
        destinations = [{"chat_id": "123", "token": "tok"}]

        self.state_repo.get_last_published_hash.return_value = "old_hash"

        mock_pub_instance = Mock()
        MockPublisher.return_value = mock_pub_instance

        # Run
        self.pipeline.run(build_result, destinations)

        # Verify
        mock_pub_instance.publish.assert_called_once()
        # The code defaults unique_id to route_name if unique_id is missing in build_result
        # In this test case, build_result does NOT have unique_id, so it falls back to route_name
        self.state_repo.mark_published.assert_called_with("route1", "new_hash")

    def test_skip_same_content(self):
        build_result = {
            "route_name": "route1",
            "artifact_hash": "same_hash",
            "format": "fmt1"
        }
        destinations = [{"chat_id": "123"}]

        self.state_repo.get_last_published_hash.return_value = "same_hash"

        with patch("mergebot.pipeline.publish.TelegramPublisher") as MockPublisher:
            self.pipeline.run(build_result, destinations)
            MockPublisher.assert_not_called()

if __name__ == '__main__':
    unittest.main()
