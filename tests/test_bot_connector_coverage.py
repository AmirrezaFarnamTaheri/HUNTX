import unittest
from unittest.mock import MagicMock, patch
import json
import urllib.error
from huntx.connectors.telegram.connector import TelegramConnector


class TestBotConnectorCoverage(unittest.TestCase):
    def setUp(self):
        self.token = "123:ABC"
        self.chat_id = "123456"
        self.connector = TelegramConnector(self.token, self.chat_id)
        TelegramConnector._shared_state = {}

    def _create_mock_response(self, content):
        m = MagicMock()
        m.__enter__.return_value = m
        m.__exit__.return_value = None
        m.read.return_value = content
        return m

    @patch("urllib.request.urlopen")
    def test_make_request_retry_success(self, mock_urlopen):
        # Fail twice, then succeed
        mock_error = urllib.error.URLError("Network unreachable")

        mock_success = self._create_mock_response(json.dumps({"ok": True}).encode("utf-8"))

        mock_urlopen.side_effect = [mock_error, mock_error, mock_success]

        res = self.connector._make_request("getMe")
        self.assertTrue(res["ok"])
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("urllib.request.urlopen")
    def test_make_request_retry_failure(self, mock_urlopen):
        mock_error = urllib.error.URLError("Network unreachable")
        mock_urlopen.side_effect = mock_error

        res = self.connector._make_request("getMe")
        self.assertFalse(res["ok"])
        self.assertEqual(mock_urlopen.call_count, 4)

    @patch("urllib.request.urlopen")
    def test_download_file_retry(self, mock_urlopen):
        mock_error = urllib.error.URLError("Fail")
        mock_success = self._create_mock_response(b"filedata")

        mock_urlopen.side_effect = [mock_error, mock_success]

        data = self.connector._download_file("path/to/file")
        self.assertEqual(data, b"filedata")
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_download_file_fail(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Fatal")
        data = self.connector._download_file("path")
        self.assertIsNone(data)

    def test_list_new_filtering_logic_detailed(self):
        with patch.object(self.connector, "_make_request") as mock_req:
            with patch.object(self.connector, "_download_file") as mock_dl:
                updates = [
                    {
                        "update_id": 10,
                        "message": {
                            "message_id": 100,
                            "chat": {"id": 123456},
                            "date": 2000000000,
                            "document": {"file_id": "f1", "file_name": "valid.txt", "file_size": 100},
                        },
                    },
                ]

                mock_req.side_effect = [
                    {"ok": True, "result": updates},
                    {"ok": True, "result": []},
                    {"ok": True, "result": {"file_path": "p1"}},
                ]

                mock_dl.return_value = b"data"

                items = list(self.connector.list_new())

                self.assertEqual(len(items), 1)
                self.assertEqual(items[0].external_id, "100")


if __name__ == "__main__":
    unittest.main()
