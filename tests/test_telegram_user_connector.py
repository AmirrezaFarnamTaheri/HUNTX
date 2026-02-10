import unittest
from unittest.mock import MagicMock, patch
import datetime
import logging
from huntx.connectors.telegram_user.connector import TelegramUserConnector


class TestTelegramUserConnector(unittest.TestCase):
    def setUp(self):
        self.api_id = 12345
        self.api_hash = "fake_hash"
        self.session = "fake_session"
        self.peer = "@test_channel"
        self.connector = TelegramUserConnector(self.api_id, self.api_hash, self.session, self.peer)

        # Capture logs
        self.logger = logging.getLogger("huntx.connectors.telegram_user.connector")
        self.logger.setLevel(logging.DEBUG)

    def _set_mock_client(self, mock_client):
        """Helper to inject a mock client into the thread-local storage."""
        if not hasattr(TelegramUserConnector._local, "clients"):
            TelegramUserConnector._local.clients = {}
        TelegramUserConnector._local.clients[(self.api_id, self.session)] = mock_client

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_initialization(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Clear local state to force initialization
        if hasattr(TelegramUserConnector._local, "clients"):
            TelegramUserConnector._local.clients = {}

        client = self.connector._client()

        mock_client_cls.assert_called_with(mock_session_cls.return_value, self.api_id, self.api_hash)
        self.assertEqual(client, mock_client)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_text(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        msg1 = MagicMock()
        msg1.id = 100
        msg1.message = "Hello World"
        msg1.media = None
        msg1.document = None
        msg1.date = datetime.datetime.now()
        # Explicitly clear unwanted media attrs so MagicMock doesn't return truthy
        for attr in ("photo", "video", "gif", "sticker", "voice", "audio", "video_note"):
            setattr(msg1, attr, None)

        mock_client.iter_messages.return_value = [msg1]

        items = list(self.connector.list_new())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "100")
        self.assertEqual(items[0].data, b"Hello World")
        self.assertEqual(items[0].metadata["filename"], "msg_100.txt")
        self.assertEqual(self.connector.offset, 100)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_media(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        msg2 = MagicMock()
        msg2.id = 101
        msg2.message = None
        msg2.media = True
        msg2.file.size = 1024
        msg2.file.name = "image.png"
        msg2.date = datetime.datetime.now()

        mock_client.iter_messages.return_value = [msg2]
        mock_client.download_media.return_value = b"fake_image_bytes"

        items = list(self.connector.list_new())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "101_media")
        self.assertEqual(items[0].data, b"fake_image_bytes")
        self.assertEqual(items[0].metadata["filename"], "image.png")
        self.assertEqual(self.connector.offset, 101)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_skip_large_file(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        msg3 = MagicMock()
        msg3.id = 102
        msg3.message = None
        msg3.media = True
        msg3.file.size = 30 * 1024 * 1024  # 30MB
        msg3.date = datetime.datetime.now()

        mock_client.iter_messages.return_value = [msg3]

        items = list(self.connector.list_new())
        self.assertEqual(len(items), 0)
        self.assertEqual(self.connector.offset, 102)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_accept_20mb_file(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        msg = MagicMock()
        msg.id = 103
        msg.message = None
        msg.media = True
        msg.file.size = 20 * 1024 * 1024  # 20MB - should be accepted
        msg.file.name = "valid_config.txt"
        msg.date = datetime.datetime.now()

        mock_client.iter_messages.return_value = [msg]
        mock_client.download_media.return_value = b"config content"

        items = list(self.connector.list_new())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "103_media")
        self.assertEqual(items[0].metadata["filename"], "valid_config.txt")
        self.assertEqual(self.connector.offset, 103)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_mixed_content_with_failures(self, mock_client_cls, mock_session_cls):
        """Test a mix of text, media, skipped media, and download errors."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        _unwanted = ("photo", "video", "gif", "sticker", "voice", "audio", "video_note")

        # Msg 1: Text only
        msg1 = MagicMock()
        msg1.id = 200
        msg1.message = "Text Message"
        msg1.media = None
        msg1.document = None
        msg1.date = datetime.datetime.now()
        for attr in _unwanted:
            setattr(msg1, attr, None)

        # Msg 2: Media too large (document)
        msg2 = MagicMock()
        msg2.id = 201
        msg2.message = None
        msg2.media = True
        msg2.document = True
        msg2.file.size = 30 * 1024 * 1024  # 30MB
        msg2.file.name = "huge.bin"
        msg2.file.ext = ".bin"
        msg2.date = datetime.datetime.now()
        for attr in _unwanted:
            setattr(msg2, attr, None)

        # Msg 3: Media download failure (document)
        msg3 = MagicMock()
        msg3.id = 202
        msg3.message = None
        msg3.media = True
        msg3.document = True
        msg3.file.size = 1024
        msg3.file.name = "broken.conf"
        msg3.file.ext = ".conf"
        msg3.date = datetime.datetime.now()
        for attr in _unwanted:
            setattr(msg3, attr, None)

        # Msg 4: Empty message (skipped)
        msg4 = MagicMock()
        msg4.id = 203
        msg4.message = ""
        msg4.media = None
        msg4.document = None
        msg4.date = datetime.datetime.now()
        for attr in _unwanted:
            setattr(msg4, attr, None)

        mock_client.iter_messages.return_value = [msg4, msg3, msg2, msg1]

        # Setup download behavior
        def download_side_effect(message, file):
            if message.id == 202:
                raise Exception("Download timeout")
            return b"content"

        mock_client.download_media.side_effect = download_side_effect

        items = list(self.connector.list_new())

        # Pass 1 yields text from msg1; pass 2 processes documents (msg2 too large, msg3 fails download)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "200")

        # Offset should update to the last processed message
        self.assertEqual(self.connector.offset, 203)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_get_state(self, mock_client_cls, mock_session_cls):
        self.connector.offset = 500
        state = self.connector.get_state()
        self.assertEqual(state, {"offset": 500})

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_state_update_on_list_new(self, mock_client_cls, mock_session_cls):
        """Test that list_new updates internal offset from state if provided."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True
        mock_client.iter_messages.return_value = []

        self.connector.offset = 100

        # Case 1: State offset is higher -> Update
        list(self.connector.list_new(state={"offset": 200}))
        self.assertEqual(self.connector.offset, 200)

        # Case 2: State offset is lower -> Ignore (keep current)
        list(self.connector.list_new(state={"offset": 150}))
        self.assertEqual(self.connector.offset, 200)

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_connection_handling(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)

        # Test connect call if not connected
        mock_client.is_connected.return_value = False
        mock_client.iter_messages.return_value = []
        list(self.connector.list_new())
        mock_client.connect.assert_called_once()

        mock_client.connect.reset_mock()

        # Test no connect call if already connected
        mock_client.is_connected.return_value = True
        list(self.connector.list_new())
        mock_client.connect.assert_not_called()

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_list_new_exceptions(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)

        mock_client.is_connected.side_effect = Exception("Connect fail")
        with self.assertRaises(Exception):
            list(self.connector.list_new())

        mock_client.is_connected.side_effect = None
        mock_client.is_connected.return_value = True

        mock_client.iter_messages.side_effect = Exception("Iter fail")
        with self.assertRaises(Exception):
            list(self.connector.list_new())

    @patch("huntx.connectors.telegram_user.connector.StringSession")
    @patch("huntx.connectors.telegram_user.connector.TelegramClient")
    def test_resolve_peer_error_handled(self, mock_client_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self._set_mock_client(mock_client)
        mock_client.is_connected.return_value = True

        self.connector.peer = "-10012345"

        with patch("telethon.utils.resolve_id", side_effect=Exception("Resolve fail")):
            mock_client.iter_messages.return_value = []
            list(self.connector.list_new())

            args, kwargs = mock_client.iter_messages.call_args
            self.assertEqual(args[0], "-10012345")


if __name__ == "__main__":
    unittest.main()
