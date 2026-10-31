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
        first.__enter__()
        first._client()

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
        connector.__enter__()
        connector._client()

        connector.cleanup()
        connector.cleanup()

        client.disconnect.assert_called_once_with()

    def test_unentered_duplicate_cannot_destroy_owned_client(self) -> None:
        first = _connector("shared-unentered")
        duplicate = _connector("shared-unentered")
        client = MagicMock()
        client.is_connected.return_value = True
        first.__enter__()
        try:
            TelegramUserConnector._local.clients[first._client_key] = client
            self.assertIs(first._client(), client)
            duplicate.cleanup()
            client.disconnect.assert_not_called()
            self.assertIs(TelegramUserConnector._local.clients[first._client_key], client)
            with self.assertRaisesRegex(RuntimeError, "session.*busy|session.*owned"):
                duplicate._client()
        finally:
            first.cleanup()
        client.disconnect.assert_called_once()

    def test_cleanup_log_never_exposes_session_or_exception_text(self) -> None:
        fake_session = "SENSITIVE_SESSION_STRING_TEST_ONLY"
        connector = _connector(fake_session)
        client = MagicMock()
        client.is_connected.return_value = True
        client.disconnect.side_effect = RuntimeError("disconnection from " + fake_session)
        connector.__enter__()
        TelegramUserConnector._local.clients[connector._client_key] = client
        connector._client()
        with self.assertLogs("huntx.connectors.telegram_user.connector", level="WARNING") as logs:
            connector.cleanup()
        self.assertNotIn(fake_session, "\\n".join(logs.output))

    def test_lock_registry_does_not_store_raw_session_secrets(self) -> None:
        session = "FAKE_HIGH_ENTROPY_SESSION_PRIVATE_TEST"
        connector = _connector(session)
        connector.__enter__()
        try:
            self.assertFalse(
                any(session in str(key) for key in TelegramUserConnector._session_locks),
                "session credentials must never persist as registry keys",
            )
        finally:
            connector.cleanup()

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
        await first.__aenter__()
        first._client()

        await first.cleanup_async()

        first_client.disconnect.assert_awaited_once_with()
        second_client.disconnect.assert_not_awaited()
        self.assertNotIn(first_key, TelegramUserConnector._local.clients)
        self.assertIs(TelegramUserConnector._local.clients[second_key], second_client)

    async def test_unentered_async_duplicate_cannot_destroy_owned_client(self) -> None:
        first = _connector("shared-async-unentered")
        duplicate = _connector("shared-async-unentered")
        client = MagicMock()
        client.is_connected.return_value = True
        client.disconnect = AsyncMock()
        await first.__aenter__()
        try:
            TelegramUserConnector._local.clients[first._client_key] = client
            self.assertIs(first._client(), client)
            await duplicate.cleanup_async()
            client.disconnect.assert_not_awaited()
            self.assertIn(first._client_key, TelegramUserConnector._local.clients)
        finally:
            await first.cleanup_async()
        client.disconnect.assert_awaited_once_with()

    async def test_cleanup_sync_after_async_acquisition_releases_owned_lock(self) -> None:
        owner = _connector("mispaired-async")
        waiter = _connector("mispaired-async")
        await owner.__aenter__()
        owner.cleanup()
        await asyncio.wait_for(waiter.__aenter__(), timeout=0.5)
        await waiter.cleanup_async()

    async def test_connected_async_owner_requires_async_cleanup(self) -> None:
        session = "must-await-cleanup"
        owner = _connector(session)
        client = MagicMock()
        client.is_connected.return_value = True
        client.disconnect = AsyncMock()
        await owner.__aenter__()
        TelegramUserConnector._local.clients[owner._client_key] = client
        owner._client()
        with self.assertRaisesRegex(RuntimeError, "cleanup_async"):
            owner.cleanup()
        self.assertIsNotNone(owner._async_lock)
        client.disconnect.assert_not_awaited()
        await owner.cleanup_async()
        client.disconnect.assert_awaited_once_with()

    async def test_connect_error_logs_only_exception_type(self) -> None:
        marker = "FAKE_SECRET_CONNECT_EXCEPTION_TEST"
        owner = _connector("safe-session")
        client = MagicMock()
        client.is_connected.return_value = False
        client.connect = AsyncMock(side_effect=RuntimeError(marker))
        with self.assertLogs("huntx.connectors.telegram_user.connector", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                await owner._ensure_connected_async(client)
        self.assertNotIn(marker, "\\n".join(logs.output))

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

    async def test_sync_owner_blocks_async_connector_for_the_same_session(self) -> None:
        """Sync and async contexts must serialize access to one MTProto session."""
        sync_owner = _connector("cross-mode")
        async_waiter = _connector("cross-mode")
        sync_owner.__enter__()
        waiter = asyncio.create_task(async_waiter.__aenter__())
        try:
            await asyncio.sleep(0.05)
            self.assertFalse(waiter.done(), "async connector bypassed sync session owner")
        finally:
            sync_owner.cleanup()
        await asyncio.wait_for(waiter, timeout=1.0)
        await async_waiter.cleanup_async()

    async def test_async_owner_blocks_sync_connector_for_the_same_session(self) -> None:
        """A sync thread must not enter while an async owner holds the session."""
        async_owner = _connector("cross-mode-reverse")
        sync_waiter = _connector("cross-mode-reverse")
        await async_owner.__aenter__()
        started = threading.Event()
        acquired = threading.Event()

        def sync_worker():
            started.set()
            sync_waiter.__enter__()
            try:
                acquired.set()
            finally:
                sync_waiter.cleanup()

        thread = threading.Thread(target=sync_worker)
        thread.start()
        try:
            self.assertTrue(started.wait(timeout=1.0))
            await asyncio.sleep(0.05)
            self.assertFalse(acquired.is_set(), "sync connector bypassed async session owner")
        finally:
            await async_owner.cleanup_async()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(acquired.is_set())
