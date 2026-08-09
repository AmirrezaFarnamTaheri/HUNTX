"""Tests for the sync/async bridging helper ``AsyncSyncIterator``.

Guards the loop-handling contract: synchronous iteration must work both when
no event loop is running (the plain test/CLI path) and when it is invoked from
*within* a running loop (which the previous ``get_event_loop`` +
``run_until_complete`` implementation crashed on).
"""

import asyncio
import unittest

from huntx.connectors.base import AsyncSyncIterator, run_sync


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


class TestRunSync(unittest.TestCase):
    """``run_sync`` is the shared sync bridge used by connectors and both
    orchestrator entrypoints, replacing deprecated get_event_loop() usage."""

    def test_returns_coroutine_result(self):
        async def coro():
            return 7

        self.assertEqual(run_sync(coro()), 7)

    def test_propagates_exception(self):
        async def boom():
            raise ValueError("kaboom")

        with self.assertRaisesRegex(ValueError, "kaboom"):
            run_sync(boom())

    def test_works_from_within_running_loop(self):
        # The case the old get_event_loop() + run_until_complete pattern
        # crashed on with "This event loop is already running".
        async def inner():
            return "inner-done"

        async def outer():
            return run_sync(inner())

        self.assertEqual(asyncio.run(outer()), "inner-done")

    def test_exception_propagates_from_within_running_loop(self):
        async def boom():
            raise RuntimeError("nested-boom")

        async def outer():
            return run_sync(boom())

        with self.assertRaisesRegex(RuntimeError, "nested-boom"):
            asyncio.run(outer())

    def test_does_not_leave_a_loop_set_on_the_thread(self):
        # new_event_loop() + set_event_loop() (the old pattern) leaked a loop
        # that was never closed; asyncio.run cleans up after itself.
        async def coro():
            return None

        run_sync(coro())
        with self.assertRaises(RuntimeError):
            asyncio.get_running_loop()


if __name__ == "__main__":
    unittest.main()
