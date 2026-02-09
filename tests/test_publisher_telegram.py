import unittest
import json
from unittest.mock import MagicMock, patch
from huntx.publishers.telegram.publisher import TelegramPublisher


class TestTelegramPublisher(unittest.TestCase):
    def setUp(self):
        self.token = "fake_token"
        self.publisher = TelegramPublisher(self.token)

    @patch("urllib.request.urlopen")
    def test_publish_success(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = self.publisher.publish("chat123", b"filecontent", "test.txt", "caption")

        self.assertTrue(res["ok"])

        # Verify request
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.full_url, f"https://api.telegram.org/bot{self.token}/sendDocument")

        # Verify multipart body roughly
        self.assertIn(b'Content-Disposition: form-data; name="chat_id"', req.data)
        self.assertIn(b"chat123", req.data)
        self.assertIn(b'Content-Disposition: form-data; name="caption"', req.data)
        self.assertIn(b"caption", req.data)
        self.assertIn(b'filename="test.txt"', req.data)
        self.assertIn(b"filecontent", req.data)

    @patch("urllib.request.urlopen")
    def test_publish_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network Error")

        with self.assertRaises(Exception):
            self.publisher.publish("chat123", b"data", "file")
