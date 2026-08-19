import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from huntx.bot.delivery import DeliveryMixin
from huntx.state.db import open_db


class _Harness(DeliveryMixin):
    def __init__(self, root: Path):
        self.db = open_db(root / "state.db")
        self.client = MagicMock()
        self.client.send_message = AsyncMock()
        self.client.send_file = AsyncMock()
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO bot_users
                    (user_id, chat_id, registered_at, approved, muted)
                VALUES ('123', '123', 0, 1, 0)
                """)


class DeliveryResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_sends_only_file_that_did_not_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            files = [(first, "first"), (second, "second")]
            harness = _Harness(root)
            harness.client.send_file.side_effect = [None, RuntimeError("transient")]

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent, failed = await harness._deliver_files_to_user(
                    {"user_id": "123", "chat_id": "123"},
                    files,
                )
            self.assertEqual((sent, failed), (1, 1))

            harness.client.send_file.reset_mock()
            harness.client.send_file.side_effect = None
            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent, failed = await harness._deliver_files_to_user(
                    {"user_id": "123", "chat_id": "123"},
                    files,
                )

            self.assertEqual((sent, failed), (1, 0))
            harness.client.send_file.assert_awaited_once()
            self.assertEqual(harness.client.send_file.await_args.args[1], second)

    async def test_changed_content_with_same_filename_is_redelivered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact.txt"
            artifact.write_text("v1", encoding="utf-8")
            harness = _Harness(root)
            user = {"user_id": "123", "chat_id": "123"}

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                await harness._deliver_files_to_user(user, [(artifact, "artifact")])
            artifact.write_text("v2", encoding="utf-8")
            harness.client.send_file.reset_mock()

            with patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
                sent, failed = await harness._deliver_files_to_user(
                    user,
                    [(artifact, "artifact")],
                )

            self.assertEqual((sent, failed), (1, 0))
            harness.client.send_file.assert_awaited_once()
            expected = hashlib.sha256(b"v2").hexdigest()
            with harness.db.connect() as conn:
                row = conn.execute("""
                    SELECT artifact_hash FROM bot_delivery_items
                    WHERE user_id = '123' ORDER BY delivered_at DESC LIMIT 1
                    """).fetchone()
            self.assertEqual(row["artifact_hash"], expected)


if __name__ == "__main__":
    unittest.main()
