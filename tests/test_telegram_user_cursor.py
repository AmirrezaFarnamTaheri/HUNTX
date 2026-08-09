import unittest

from huntx.connectors.telegram_user.connector import (
    TelegramUserConnector,
    TelegramUserItem,
)


class TelegramUserCursorTests(unittest.TestCase):
    def test_text_and_document_cursors_advance_only_when_acknowledged(self):
        connector = TelegramUserConnector(
            1,
            "hash",
            "session",
            "@peer",
            state={"offset": 5},
        )
        self.assertEqual(
            connector.get_state(),
            {"offset": 5, "text_offset": 5, "document_offset": 5},
        )

        connector.acknowledge(
            [
                TelegramUserItem(
                    "6",
                    b"text",
                    {
                        "filename": "msg_6.txt",
                        "_cursor_kind": "text",
                        "_cursor_id": 6,
                    },
                ),
                TelegramUserItem(
                    "9_media",
                    b"file",
                    {
                        "filename": "file.bin",
                        "_cursor_kind": "document",
                        "_cursor_id": 9,
                    },
                ),
            ]
        )

        self.assertEqual(
            connector.get_state(),
            {"offset": 6, "text_offset": 6, "document_offset": 9},
        )


if __name__ == "__main__":
    unittest.main()
