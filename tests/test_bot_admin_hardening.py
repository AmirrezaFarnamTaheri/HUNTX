import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from huntx.bot.admin import AdminMixin


class _AdminHarness(AdminMixin):
    def __init__(self):
        self._pipeline_task = None
        self.client = MagicMock()
        self.client.send_message = AsyncMock()
        self.deliver_updates_active = AsyncMock()
        self.repo = MagicMock()
        self.blocking_runs = 0
        self.release_run = threading.Event()

    def _run_pipeline_blocking(self):
        self.blocking_runs += 1
        if not self.release_run.wait(timeout=5):
            raise TimeoutError("test did not release background pipeline")


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
        self.assertFalse(started_task.done())

        harness.release_run.set()
        await started_task

        self.assertIsNone(harness._pipeline_task)
        self.assertEqual(harness.blocking_runs, 1)
        harness.deliver_updates_active.assert_awaited_once()
        harness.client.send_message.assert_awaited_once()

    async def test_prune_keeps_hash_still_referenced_by_live_row(self):
        harness = _AdminHarness()
        harness.repo.prune_old_data.return_value = {
            "seen_files": 1,
            "records": 0,
            "published_artifacts": 0,
            "raw_hashes": ["shared-hash", "orphan-hash"],
        }
        harness.repo.get_all_known_hashes.return_value = {"shared-hash"}

        event = MagicMock()
        event.answer = AsyncMock()
        message = MagicMock()
        message.edit = AsyncMock()
        event.respond = AsyncMock(return_value=message)

        raw_store = MagicMock()
        raw_store.prune_by_hashes.return_value = 1

        with patch("huntx.store.raw_store.RawStore", return_value=raw_store):
            await harness._perform_admin_prune(event, 30)

        harness.repo.prune_old_data.assert_called_once_with(30)
        harness.repo.get_all_known_hashes.assert_called_once_with()
        raw_store.prune_by_hashes.assert_called_once_with(["orphan-hash"])
        message.edit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
