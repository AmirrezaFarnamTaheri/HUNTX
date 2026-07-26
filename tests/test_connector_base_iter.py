"""Tests for the sync/async bridging helper ``AsyncSyncIterator``.

Guards the loop-handling contract: synchronous iteration must work both when
no event loop is running (the plain test/CLI path) and when it is invoked from
*within* a running loop (which the previous ``get_event_loop`` +
``run_until_complete`` implementation crashed on).
"""

import asyncio
import unittest

from huntx.connectors.base import AsyncSyncIterator


async def _gen(values):
    for v in values:
        yield v


class TestAsyncSyncIterator(unittest.TestCase):
    def test_sync_iteration_without_running_loop(self):
        it = AsyncSyncIterator(_gen([1, 2, 3]))
        self.assertEqual(list(it), [1, 2, 3])

    def test_async_iteration(self):
        async def run():
            return [v async for v in AsyncSyncIterator(_gen(["a", "b"]))]

        self.assertEqual(asyncio.run(run()), ["a", "b"])

    def test_sync_iteration_from_within_running_loop(self):
        # Reproduces the re-entrancy scenario: calling the *sync* iterator while
        # an event loop is already running on this thread must not raise
        # "This event loop is already running".
        async def run():
            it = AsyncSyncIterator(_gen([10, 20, 30]))
            # list() drives __iter__ synchronously inside the running loop.
            return list(it)

        self.assertEqual(asyncio.run(run()), [10, 20, 30])

    def test_empty_generator(self):
        self.assertEqual(list(AsyncSyncIterator(_gen([]))), [])


if __name__ == "__main__":
    unittest.main()
