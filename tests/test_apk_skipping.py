import unittest
import time
from unittest.mock import MagicMock, patch
from mergebot.connectors.telegram.connector import TelegramConnector, TelegramItem
from mergebot.connectors.telegram_user.connector import TelegramUserConnector, SourceItem

class TestApkSkipping(unittest.TestCase):
    def setUp(self):
        # Clear shared state to prevent test pollution
        TelegramConnector._shared_state = {}
        TelegramUserConnector._shared_clients = {}

    def test_telegram_connector_skips_apk(self):
        connector = TelegramConnector("token", "123")
        now = time.time()

        # Mock _make_request to return updates with an APK file
        with patch.object(connector, '_make_request') as mock_request, \
             patch.object(connector, '_download_file') as mock_download:

            mock_request.side_effect = [
                {
                    "ok": True,
                    "result": [{
                        "update_id": 1,
                        "message": {
                            "message_id": 100,
                            "date": now,
                            "chat": {"id": 123},
                            "document": {
                                "file_id": "file_apk",
                                "file_name": "malicious.apk",
                                "file_size": 1000
                            }
                        }
                    }]
                },
                {"ok": True, "result": []}, # End updates loop
                {"ok": True, "result": {"file_path": "path/apk"}} # getFile - Should NOT be called if skipped
            ]
            mock_download.return_value = b"apk_content"

            # Check logic: The connector iterates updates.
            # If APK logic works, it skips processing and does not call getFile.
            # So mock_request will be called 2 times (getUpdates x2).
            # If we provide 3 side effects, the 3rd one won't be used.

            items = list(connector.list_new())

            self.assertEqual(len(items), 0)

            # Verify getFile was NOT called.
            # mock_request.call_args_list should show only getUpdates
            calls = mock_request.call_args_list
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0][0], "getUpdates")
            self.assertEqual(calls[1][0][0], "getUpdates")


    def test_telegram_connector_mixed_content(self):
        connector = TelegramConnector("token", "123")
        now = time.time()

        # Mock update with text AND valid file
        with patch.object(connector, '_make_request') as mock_request, \
             patch.object(connector, '_download_file') as mock_download:

            # Correct sequence:
            # 1. getUpdates -> returns update
            # 2. getUpdates -> returns empty (end loop)
            # 3. getFile -> returns info (called during processing)
            mock_request.side_effect = [
                {
                    "ok": True,
                    "result": [{
                        "update_id": 2,
                        "message": {
                            "message_id": 200,
                            "date": now,
                            "chat": {"id": 123},
                            "text": "Some config text",
                            "document": {
                                "file_id": "file_conf",
                                "file_name": "good.conf",
                                "file_size": 1000
                            }
                        }
                    }]
                },
                {"ok": True, "result": []},
                {"ok": True, "result": {"file_path": "path/good.conf"}}
            ]

            mock_download.return_value = b"conf_content"

            items = list(connector.list_new())

            self.assertEqual(len(items), 2)

            text_item = next((i for i in items if i.external_id.endswith("_text")), None)
            file_item = next((i for i in items if not i.external_id.endswith("_text")), None)

            self.assertIsNotNone(text_item)
            self.assertEqual(text_item.data.decode("utf-8"), "Some config text")

            self.assertIsNotNone(file_item)
            self.assertEqual(file_item.data, b"conf_content")
            self.assertEqual(file_item.metadata["filename"], "good.conf")

    def test_telegram_user_connector_skips_apk(self):
        connector = TelegramUserConnector(1, "hash", "session", "peer")

        mock_client = MagicMock()
        connector._shared_clients[(1, "session")] = mock_client

        # Mock message with APK
        msg_apk = MagicMock()
        msg_apk.id = 300
        msg_apk.date.timestamp.return_value = time.time()
        msg_apk.message = None
        msg_apk.media = True
        msg_apk.file.name = "bad.apk"
        msg_apk.file.ext = ".apk"
        msg_apk.file.size = 1000

        mock_client.iter_messages.return_value = [msg_apk]
        mock_client.is_connected.return_value = True

        items = list(connector.list_new())

        self.assertEqual(len(items), 0)
        mock_client.download_media.assert_not_called()

    def test_telegram_user_connector_mixed_content(self):
        connector = TelegramUserConnector(1, "hash", "session", "peer")

        mock_client = MagicMock()
        connector._shared_clients[(1, "session")] = mock_client

        # Mock message with Text AND valid file
        msg_mixed = MagicMock()
        msg_mixed.id = 400
        msg_mixed.date.timestamp.return_value = time.time()
        msg_mixed.message = "Config text"
        msg_mixed.media = True
        msg_mixed.file.name = "good.ovpn"
        msg_mixed.file.size = 1000

        mock_client.iter_messages.return_value = [msg_mixed]
        mock_client.is_connected.return_value = True
        mock_client.download_media.return_value = b"ovpn_content"

        items = list(connector.list_new())

        self.assertEqual(len(items), 2)

        # Check items
        text_ids = [i.external_id for i in items]
        self.assertIn("400", text_ids)
        self.assertIn("400_media", text_ids)

if __name__ == '__main__':
    unittest.main()
