import os
import sqlite3
import time
import unittest
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

from huntx.bot.delivery import DeliveryMixin, FloodWaitError
from huntx.bot.interactive import InteractiveBot


def _flood_wait(seconds: int):
    try:
        exc = FloodWaitError(request=None, capture=seconds)
    except TypeError:
        exc = FloodWaitError()
    exc.seconds = seconds
    return exc


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *_args):
        self.conn.commit()


class _DB:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return _ConnContext(self.conn)


class TestCallbackHardening(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = object.__new__(InteractiveBot)
        self.bot._user_cooldowns = OrderedDict()
        self.bot._is_admin = MagicMock(return_value=False)

    async def test_callback_rate_limit_is_enforced(self):
        event = MagicMock()
        event.sender_id = 7
        event.answer = AsyncMock()
        event.respond = AsyncMock()

        self.assertTrue(await self.bot._check_rate_limit(event, 10))
        self.assertFalse(await self.bot._check_rate_limit(event, 10))
        event.answer.assert_awaited_once()

    async def test_admin_is_exempt_from_rate_limit(self):
        self.bot._is_admin = MagicMock(return_value=True)
        event = MagicMock()
        event.sender_id = 7
        event.answer = AsyncMock()

        self.assertTrue(await self.bot._check_rate_limit(event, 10))
        self.assertTrue(await self.bot._check_rate_limit(event, 10))
        event.answer.assert_not_awaited()

    def test_cooldown_storage_is_bounded_and_pruned(self):
        self.bot._COOLDOWN_MAX_ENTRIES = 3
        self.bot._COOLDOWN_TTL_SECONDS = 10
        now = time.time()
        self.bot._user_cooldowns.update(
            [(1, now - 100), (2, now - 1), (3, now - 1), (4, now - 1), (5, now - 1)]
        )

        self.bot._prune_cooldowns(now)

        self.assertNotIn(1, self.bot._user_cooldowns)
        self.assertLessEqual(len(self.bot._user_cooldowns), 3)

    async def test_callback_failure_does_not_expose_exception_text(self):
        self.bot._check_rate_limit = AsyncMock(return_value=True)
        self.bot._send_format_to_user = AsyncMock(side_effect=RuntimeError("secret detail"))
        event = MagicMock()
        event.data = b"get:npvt"
        event.sender_id = 8
        event.chat_id = 9
        event.answer = AsyncMock()

        await self.bot._on_callback(event)

        final_message = event.answer.await_args_list[-1].args[0]
        self.assertNotIn("secret detail", final_message)
        self.assertIn("try again", final_message.lower())


class TestTokenIsolation(unittest.TestCase):
    @patch("huntx.bot.interactive.TelegramClient")
    def test_shared_token_fails_closed(self, _client):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "same"}, clear=False):
            os.environ.pop("HUNTX_ALLOW_SHARED_BOT_TOKEN", None)
            with self.assertRaises(RuntimeError):
                InteractiveBot("same", 1, "hash")

    @patch("huntx.bot.interactive.TelegramClient")
    @patch("huntx.bot.interactive.open_db")
    @patch("huntx.bot.interactive.ArtifactStore")
    @patch("huntx.bot.interactive.StateRepo")
    def test_explicit_shared_token_override_is_allowed(self, repo, store, open_db, _client):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        open_db.return_value = _DB(conn)
        with patch.dict(
            os.environ,
            {"TELEGRAM_TOKEN": "same", "HUNTX_ALLOW_SHARED_BOT_TOKEN": "true"},
            clear=False,
        ):
            bot = InteractiveBot("same", 1, "hash")
        self.assertEqual(bot.token, "same")
        conn.close()


class _DeliveryHarness(DeliveryMixin):
    pass


class TestDeliveryRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_floodwait_retries_within_cap(self):
        harness = _DeliveryHarness()
        calls = 0

        async def method():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _flood_wait(1)
            return "ok"

        with patch.dict(
            os.environ,
            {"HUNTX_FLOODWAIT_MAX_SECONDS": "5", "HUNTX_FLOODWAIT_MAX_RETRIES": "2"},
            clear=False,
        ), patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()):
            result = await harness._send_with_floodwait(method)

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 2)

    async def test_floodwait_above_cap_is_not_retried(self):
        harness = _DeliveryHarness()
        calls = 0

        async def method():
            nonlocal calls
            calls += 1
            raise _flood_wait(30)

        with patch.dict(
            os.environ,
            {"HUNTX_FLOODWAIT_MAX_SECONDS": "5", "HUNTX_FLOODWAIT_MAX_RETRIES": "2"},
            clear=False,
        ):
            with self.assertRaises(FloodWaitError):
                await harness._send_with_floodwait(method)

        self.assertEqual(calls, 1)

    def test_checkpoint_persists_partial_progress(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE bot_users (
                user_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                registered_at REAL NOT NULL,
                last_delivered_at REAL DEFAULT 0
            );
            CREATE TABLE bot_delivery_checkpoint (
                user_id TEXT PRIMARY KEY,
                attempted INTEGER NOT NULL,
                sent INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                last_error TEXT,
                updated_at REAL NOT NULL
            );
            INSERT INTO bot_users (user_id, chat_id, registered_at) VALUES ('1', '1', 0);
            """
        )
        harness = _DeliveryHarness()
        harness.db = _DB(conn)

        harness._record_delivery_checkpoint(
            "1", attempted=3, sent=2, failed=1, error="TimeoutError"
        )

        row = conn.execute("SELECT * FROM bot_delivery_checkpoint WHERE user_id='1'").fetchone()
        self.assertEqual((row["attempted"], row["sent"], row["failed"]), (3, 2, 1))
        self.assertEqual(row["last_error"], "TimeoutError")
        self.assertGreater(
            conn.execute("SELECT last_delivered_at FROM bot_users WHERE user_id='1'").fetchone()[0],
            0,
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()