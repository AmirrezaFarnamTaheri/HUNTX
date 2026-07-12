import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from huntx.bot.admin import AdminMixin


class _AdminHarness(AdminMixin):
    def __init__(self):
        self._pipeline_task = None
        self.client = MagicMock()
        self.client.send_message = AsyncMock()
        self.deliver_updates_active = AsyncMock()
        self.blocking_runs = 0

    def _run_pipeline_blocking(self):
        self.blocking_runs += 1


class TestAdminPipelineGuard(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_duplicate_background_run(self):
        harness = _AdminHarness()
        blocker = asyncio.Event()
        existing_task = asyncio.create_task(blocker.wait())
        harness._pipeline_task = existing_task

        event = MagicMock()
        event.answer = AsyncMock()
        event.respond = AsyncMock()
        event.chat_id = 123

        try:
            await harness._trigger_background_run(event)

            self.assertIs(harness._pipeline_task, existing_task)
            self.assertEqual(harness.blocking_runs, 0)
            event.answer.assert_awaited_once_with("Pipeline is already running.")
            event.respond.assert_awaited_once()
            self.assertIn(
                "already in progress",
                event.respond.await_args.args[0],
            )
        finally:
            blocker.set()
            await existing_task

    async def test_started_task_clears_guard_after_completion(self):
        harness = _AdminHarness()

        event = MagicMock()
        event.answer = AsyncMock()
        event.respond = AsyncMock()
        event.chat_id = 456

        await harness._trigger_background_run(event)
        started_task = harness._pipeline_task

        self.assertIsNotNone(started_task)
        await started_task

        self.assertIsNone(harness._pipeline_task)
        self.assertEqual(harness.blocking_runs, 1)
        harness.deliver_updates_active.assert_awaited_once()
        harness.client.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
