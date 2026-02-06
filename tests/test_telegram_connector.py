import unittest
import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from mergebot.connectors.telegram.connector import TelegramConnector

class TestTelegramConnector(unittest.TestCase):
    def setUp(self):
        self.connector = TelegramConnector("token", "123")

    @patch('urllib.request.urlopen')
    def test_make_request_retry_success(self, mock_urlopen):
        # Setup mock to raise URLError twice, then return success
        success_response = MagicMock()
        success_response.read.return_value = json.dumps({"ok": True, "result": []}).encode('utf-8')
        success_response.__enter__.return_value = success_response

        mock_urlopen.side_effect = [
            URLError("Network unreachable"),
            URLError("Network unreachable"),
            success_response
        ]

        # Call the method
        with patch('time.sleep') as mock_sleep: # Don't actually sleep in tests
            result = self.connector._make_request("getUpdates")

        self.assertTrue(result["ok"])
        # Expecting it to handle the retries.
        # Since currently there are NO retries, this test will fail (call_count will be 1)
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch('urllib.request.urlopen')
    def test_download_file_retry_success(self, mock_urlopen):
        # Setup mock to raise URLError twice, then return success
        success_response = MagicMock()
        success_response.read.return_value = b'file_content'
        success_response.__enter__.return_value = success_response

        mock_urlopen.side_effect = [
            URLError("Network unreachable"),
            URLError("Network unreachable"),
            success_response
        ]

        # Call the method
        with patch('time.sleep') as mock_sleep:
            result = self.connector._download_file("path/to/file")

        self.assertEqual(result, b'file_content')
        self.assertEqual(mock_urlopen.call_count, 3)

if __name__ == '__main__':
    unittest.main()
