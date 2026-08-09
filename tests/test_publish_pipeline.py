import hashlib
import unittest
from unittest.mock import Mock, patch

from huntx.pipeline.publish import PublishPipeline


class TestPublishPipeline(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.state_repo.is_delivery_confirmed.return_value = False
        self.state_repo.get_delivery_state.return_value = None
        self.pipeline = PublishPipeline(self.state_repo)

    @staticmethod
    def _build(data=b"data", **overrides):
        result = {
            "route_name": "route1",
            "artifact_hash": hashlib.sha256(data).hexdigest(),
            "format": "fmt1",
            "data": data,
        }
        result.update(overrides)
        return result

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_publish_new_content(self, MockPublisher):
        build_result = self._build()
        destinations = [{"chat_id": "123", "token": "test-value"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"
        mock_pub_instance = Mock()
        MockPublisher.return_value = mock_pub_instance

        self.pipeline.run(build_result, destinations)

        mock_pub_instance.publish.assert_called_once()
        self.state_repo.mark_delivery_confirmed.assert_called_once()
        self.state_repo.mark_published.assert_called_with("route1", build_result["artifact_hash"])

    def test_skip_same_content(self):
        build_result = self._build()
        destinations = [{"chat_id": "123", "token": "tok"}]
        self.state_repo.is_delivery_confirmed.return_value = True
        self.state_repo.get_delivery_state.return_value = "confirmed"

        with patch("huntx.pipeline.publish.TelegramPublisher") as MockPublisher:
            self.pipeline.run(build_result, destinations)
            MockPublisher.assert_not_called()

    def test_unknown_outcome_blocks_automatic_resend(self):
        build_result = self._build()
        destinations = [{"chat_id": "123", "token": "tok"}]
        self.state_repo.get_delivery_state.return_value = "unknown_outcome"

        with patch("huntx.pipeline.publish.TelegramPublisher") as publisher:
            with self.assertRaisesRegex(RuntimeError, "UnknownPublicationOutcome"):
                self.pipeline.run(build_result, destinations)
        publisher.assert_not_called()

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
        build_result = self._build(b"x")
        destinations = [{"chat_id": "123", "required": False}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        result = self.pipeline.run(build_result, destinations)

        self.assertFalse(result)
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
        build_result = self._build(b"x")
        destinations = [{"chat_id": "123"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        with self.assertRaisesRegex(RuntimeError, "No token configured"):
            self.pipeline.run(build_result, destinations)

        self.state_repo.mark_published.assert_not_called()

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_partial_destination_failure_still_marks_published(self, MockPublisher):
        # Regression: a failing destination must not prevent mark_published
        # from recording the destinations that DID succeed. Otherwise
        # last_hash never advances and every destination — including the
        # ones that already got the artifact — is resent on every subsequent
        # run for as long as the one failing destination stays broken.
        build_result = self._build(unique_id="route1:fmt1")
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
        # Destination A is durably confirmed, but the route is not globally
        # complete while destination B remains failed.
        self.state_repo.mark_delivery_confirmed.assert_called_once()
        self.state_repo.mark_published.assert_not_called()

        # On retry only the failed destination is sent. This is the invariant
        # the old route-level hash checkpoint could not provide.
        confirmed_destination = self.state_repo.mark_delivery_confirmed.call_args.args[1]
        self.state_repo.is_delivery_confirmed.side_effect = (
            lambda _intent, destination_id: destination_id == confirmed_destination
        )
        self.state_repo.get_delivery_state.side_effect = lambda _intent, destination_id: (
            "confirmed" if destination_id == confirmed_destination else "failed"
        )
        bad_instance.publish.side_effect = None
        self.pipeline.run(build_result, destinations)
        good_instance.publish.assert_called_once()
        self.assertEqual(bad_instance.publish.call_count, 2)
        self.state_repo.mark_published.assert_called_once_with("route1:fmt1", build_result["artifact_hash"])

    @patch("huntx.pipeline.publish.TelegramPublisher")
    def test_all_destinations_fail_does_not_mark_published(self, MockPublisher):
        build_result = self._build(unique_id="route1:fmt1")
        destinations = [{"chat_id": "bad", "token": "tok-bad"}]
        self.state_repo.get_last_published_hash.return_value = "old_hash"

        bad_instance = Mock()
        bad_instance.publish.side_effect = RuntimeError("down")
        MockPublisher.return_value = bad_instance

        with self.assertRaises(RuntimeError):
            self.pipeline.run(build_result, destinations)

        self.state_repo.mark_published.assert_not_called()

    def test_rejects_digest_payload_mismatch(self):
        build_result = self._build()
        build_result["artifact_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            self.pipeline.run(
                build_result,
                [{"id": "primary", "chat_id": "123", "token": "tok"}],
            )

    def test_duplicate_destination_identity_is_rejected(self):
        build_result = self._build()
        destinations = [
            {"id": "primary", "chat_id": "123", "token": "tok-a"},
            {"id": "primary", "chat_id": "456", "token": "tok-b"},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate destination"):
            self.pipeline.run(build_result, destinations)


if __name__ == "__main__":
    unittest.main()
