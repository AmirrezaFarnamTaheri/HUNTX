import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from huntx.core.session_lease import (
    SessionLeaseTimeout,
    acquire_session_lease,
    session_lease_path,
)


class TestSessionLease(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_lease_is_exclusive_and_released(self) -> None:
        async with acquire_session_lease(self.root, "identity", timeout_seconds=0.1):
            lock_path = session_lease_path(self.root, "identity")
            self.assertTrue(lock_path.exists())
            with self.assertRaises(SessionLeaseTimeout):
                async with acquire_session_lease(
                    self.root,
                    "identity",
                    timeout_seconds=0.02,
                    poll_seconds=0.01,
                ):
                    pass
        self.assertFalse(lock_path.exists())

    async def test_stale_lease_is_reclaimed(self) -> None:
        lock_path = session_lease_path(self.root, "identity")
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text("stale", encoding="utf-8")
        os.utime(lock_path, (1, 1))
        async with acquire_session_lease(
            self.root,
            "identity",
            timeout_seconds=0.1,
            stale_after_seconds=1,
            poll_seconds=0.01,
        ):
            self.assertTrue(lock_path.exists())

    async def test_different_identities_do_not_block_each_other(self) -> None:
        async with acquire_session_lease(self.root, "one", timeout_seconds=0.1):
            async with acquire_session_lease(self.root, "two", timeout_seconds=0.1):
                await asyncio.sleep(0)
                self.assertTrue(session_lease_path(self.root, "one").exists())
                self.assertTrue(session_lease_path(self.root, "two").exists())


if __name__ == "__main__":
    unittest.main()