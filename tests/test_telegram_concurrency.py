import unittest
import json
from unittest.mock import patch, MagicMock
from mergebot.connectors.telegram.connector import TelegramConnector


class TestTelegramConcurrency(unittest.TestCase):
    def setUp(self):
        # Reset shared state to ensure test isolation
        TelegramConnector._shared_state = {}

        self.updates = [
            {
                "update_id": 1,
                "message": {
                    "message_id": 101,
                    "date": 2000000000,
                    "chat": {"id": -1001},
                    "document": {"file_id": "f1", "file_name": "file1.txt", "file_size": 100},
                },
            },
            {
                "update_id": 2,
                "message": {
                    "message_id": 102,
                    "date": 2000000000,
                    "chat": {"id": -1002},
                    "document": {"file_id": "f2", "file_name": "file2.txt", "file_size": 100},
                },
            },
        ]
        self.max_acked = 0

    def mock_urlopen(self, request, timeout=30):
        # Extract URL and Data
        if hasattr(request, "full_url"):
            full_url = request.full_url
            data = request.data
        else:
            full_url = request
            data = None

        resp_mock = MagicMock()
        resp_mock.__enter__.return_value = resp_mock

        if "getUpdates" in full_url:
            params = {}
            if data:
                params = json.loads(data.decode("utf-8"))

            offset = params.get("offset", 0)

            if offset > 0:
                self.max_acked = max(self.max_acked, offset - 1)

            # Return updates that are NOT confirmed
            available = [u for u in self.updates if u["update_id"] > self.max_acked]

            if offset > 0:
                available = [u for u in available if u["update_id"] >= offset]

            resp_mock.read.return_value = json.dumps({"ok": True, "result": available}).encode("utf-8")
            return resp_mock

        elif "getFile" in full_url:
            resp_mock.read.return_value = json.dumps({"ok": True, "result": {"file_path": "path/to/file"}}).encode(
                "utf-8"
            )
            return resp_mock

        elif "/file/bot" in full_url:
            resp_mock.read.return_value = b"dummy content"
            return resp_mock

        return resp_mock

    @patch("urllib.request.urlopen")
    @patch("time.sleep")  # Skip sleeps
    def test_shared_state_concurrency(self, mock_sleep, mock_urlopen):
        mock_urlopen.side_effect = self.mock_urlopen

        # Source 1: Interested in Chat -1001
        conn1 = TelegramConnector("token", "-1001")

        # Source 2: Interested in Chat -1002
        conn2 = TelegramConnector("token", "-1002")

        # Run Source 1
        items1 = list(conn1.list_new())

        # Assert Source 1 got its file
        self.assertEqual(len(items1), 1)
        self.assertEqual(items1[0].metadata["file_id"], "f1")

        # Run Source 2
        items2 = list(conn2.list_new())

        # Assert Source 2 gets its file (Verified Fix)
        self.assertEqual(len(items2), 1, "Source 2 should find 1 item")
        self.assertEqual(items2[0].metadata["file_id"], "f2")


if __name__ == "__main__":
    unittest.main()
