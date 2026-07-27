import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from huntx.connectors.telegram_user.connector import TelegramUserConnector


def _connector(session: str) -> TelegramUserConnector:
    return TelegramUserConnector(
        api_id=123,
        api_hash="hash",
        session=session,
        peer="@channel",
    )


class TestTelegramUserConnectorOwnership(unittest.TestCase):
    def setUp(self) -> None:
        TelegramUserConnector._local.clients = {}

    def tearDown(self) -> None:
        TelegramUserConnector._local.clients = {}

    def test_sync_cleanup_only_disconnects_owned_client(self) -> None:
        first = _connector("first")
        second = _connector("second")
        first_client = MagicMock()
        first_client.is_connected.return_value = True
        second_client = MagicMock()
        second_client.is_connected.return_value = True
        first_key = (first.api_id, first.session)
        second_key = (second.api_id, second.session)
        TelegramUserConnector._local.clients = {
            first_key: first_client,
            second_key: second_client,
        }

        first.cleanup()

        first_client.disconnect.assert_called_once_with()
        second_client.disconnect.assert_not_called()
        self.assertNotIn(first_key, TelegramUserConnector._local.clients)
        self.assertIs(TelegramUserConnector._local.clients[second_key], second_client)

    def test_sync_cleanup_is_idempotent(self) -> None:
        connector = _connector("owned")
        client = MagicMock()
        client.is_connected.return_value = True
        TelegramUserConnector._local.clients = {
            (connector.api_id, connector.session): client,
        }

        connector.cleanup()
        connector.cleanup()

        client.disconnect.assert_called_once_with()

    def test_distinct_sync_sessions_do_not_block_each_other(self) -> None:
        first = _connector("first")
        second = _connector("second")
        first.__enter__()
        acquired = threading.Event()

        def acquire_second() -> None:
            second.__enter__()
            acquired.set()
            second.cleanup()

        thread = threading.Thread(target=acquire_second)
        thread.start()
        self.assertTrue(acquired.wait(timeout=1.0))
        first.cleanup()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())


class TestTelegramUserConnectorAsyncOwnership(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        TelegramUserConnector._local.clients = {}

    async def asyncTearDown(self) -> None:
        TelegramUserConnector._local.clients = {}

    async def test_async_cleanup_only_disconnects_owned_client(self) -> None:
        first = _connector("first")
        second = _connector("second")
        first_client = MagicMock()
        first_client.is_connected.return_value = True
        first_client.disconnect = AsyncMock()
        second_client = MagicMock()
        second_client.is_connected.return_value = True
        second_client.disconnect = AsyncMock()
        first_key = (first.api_id, first.session)
        second_key = (second.api_id, second.session)
        TelegramUserConnector._local.clients = {
            first_key: first_client,
            second_key: second_client,
        }

        await first.cleanup_async()

        first_client.disconnect.assert_awaited_once_with()
        second_client.disconnect.assert_not_awaited()
        self.assertNotIn(first_key, TelegramUserConnector._local.clients)
        self.assertIs(TelegramUserConnector._local.clients[second_key], second_client)

    async def test_same_async_session_waits_for_owner_release(self) -> None:
        first = _connector("shared")
        second = _connector("shared")
        await first.__aenter__()
        waiting = asyncio.create_task(second.__aenter__())
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())

        await first.cleanup_async()
        await asyncio.wait_for(waiting, timeout=1.0)
        await second.cleanup_async()
