import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from huntx.bot.delivery import DeliveryMixin
from huntx.state.db import open_db


class _DeliveryHarness(DeliveryMixin):
    def __init__(self, files, root: Path, chat_id: int):
        self.artifact_store = MagicMock()
        self.artifact_store.list_archive.return_value = files
        self.client = MagicMock()
        self.client.send_file = AsyncMock()
        self.client.send_message = AsyncMock()
        self.db = open_db(root / "delivery.db")
        identity = str(chat_id)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_users
                    (user_id, chat_id, registered_at, approved, muted)
                VALUES (?, ?, 0, 1, 0)
                """,
                (identity, identity),
            )


class TestArchivedDeliveryMatching(unittest.IsolatedAsyncioTestCase):
    async def test_sends_exported_b64sub_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "all_sources_npvt_b64sub.txt"
            artifact.write_text("dGVzdA==\n", encoding="utf-8")
            harness = _DeliveryHarness([artifact], root, 123)

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent = await harness._send_latest_to_user(
                    chat_id=123,
                    fmt="b64sub",
                    days=4,
                )

            self.assertEqual(sent, 1)
            harness.artifact_store.list_archive.assert_called_once_with(days=4)
            harness.client.send_file.assert_awaited_once()
            self.assertEqual(harness.client.send_file.await_args.args[1], artifact)
            harness.client.send_message.assert_not_awaited()

    async def test_sends_exported_decoded_json_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "all_sources_npvt_decoded.json"
            artifact.write_text("{}\n", encoding="utf-8")
            harness = _DeliveryHarness([artifact], root, 456)

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent = await harness._send_latest_to_user(
                    chat_id=456,
                    fmt="decoded.json",
                    days=7,
                )

            self.assertEqual(sent, 1)
            harness.artifact_store.list_archive.assert_called_once_with(days=7)
            harness.client.send_file.assert_awaited_once()
            self.assertEqual(harness.client.send_file.await_args.args[1], artifact)
            harness.client.send_message.assert_not_awaited()

    async def test_skips_non_matching_archive_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "all_sources.ovpn"
            artifact.write_bytes(b"client\n")
            harness = _DeliveryHarness([artifact], root, 789)

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent = await harness._send_latest_to_user(
                    chat_id=789,
                    fmt="b64sub",
                    days=4,
                )

            self.assertEqual(sent, 0)
            harness.client.send_file.assert_not_awaited()
            harness.client.send_message.assert_awaited_once_with(
                789,
                "No artifacts matching `b64sub`.",
            )


if __name__ == "__main__":
    unittest.main()
