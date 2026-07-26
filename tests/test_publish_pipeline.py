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

    @patch.dict(
        "os.environ",
        {
            "CI": "0",
            "HUNTX_STRICT": "0",
            "PUBLISH_BOT_TOKEN": "",
            "TELEGRAM_TOKEN": "",
        },
        clear=False,
    )
    def test_skip_when_destination_has_no_token(self):
        build_result = {"route_name": "route1", "artifact_hash": "new_hash", "format": "fmt1", "data": b"x"}
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        result = self.pipeline.run(build_result, destinations)

        self.assertTrue(result)
        self.state_repo.mark_published.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "CI": "1",
            "HUNTX_STRICT": "0",
            "PUBLISH_BOT_TOKEN": "",
            "TELEGRAM_TOKEN": "",
        },
        clear=False,
    )
    def test_missing_destination_token_raises_in_ci(self):
        build_result = {"route_name": "route1", "artifact_hash": "new_hash", "format": "fmt1", "data": b"x"}
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        with self.assertRaisesRegex(RuntimeError, "Strict Mode Active"):
            self.pipeline.run(build_result, destinations)

        self.state_repo.mark_published.assert_not_called()

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_partial_destination_failure_still_marks_published(self, MockPublisher):
        # Regression: a failing destination must not prevent mark_published
        # from recording the destinations that DID succeed. Otherwise
        # last_hash never advances and every destination — including the
        # ones that already got the artifact — is resent on every subsequent
        # run for as long as the one failing destination stays broken.
        build_result = {
            "route_name": "route1",
            "artifact_hash": "new_hash",
            "format": "fmt1",
            "data": b"data",
            "unique_id": "route1:fmt1",
        }
        destinations = [
            {"chat_id": "good", "token": "tok-good"},
            {"chat_id": "bad", "token": "tok-bad"},
        ]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        good_instance = Mock()
        bad_instance = Mock()
        bad_instance.publish.side_effect = RuntimeError("rate limited")

        def _make_publisher(token):
            return {"tok-good": good_instance, "tok-bad": bad_instance}[token]

        MockPublisher.side_effect = _make_publisher

        with self.assertRaises(RuntimeError):
            self.pipeline.run(build_result, destinations)

        good_instance.publish.assert_called_once()
        bad_instance.publish.assert_called_once()
        # The key assertion: success was recorded despite the later failure.
        self.state_repo.mark_published.assert_called_once_with("route1:fmt1", "new_hash")

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_all_destinations_fail_does_not_mark_published(self, MockPublisher):
        build_result = {
            "route_name": "route1",
            "artifact_hash": "new_hash",
            "format": "fmt1",
            "data": b"data",
            "unique_id": "route1:fmt1",
        }
        destinations = [{"chat_id": "bad", "token": "tok-bad"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        bad_instance = Mock()
        bad_instance.publish.side_effect = RuntimeError("down")
        MockPublisher.return_value = bad_instance

        with self.assertRaises(RuntimeError):
            self.pipeline.run(build_result, destinations)

        self.state_repo.mark_published.assert_not_called()


if __name__ == "__main__":
    unittest.main()
