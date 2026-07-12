import asyncio
from pathlib import Path

import pytest

from huntx.core.session_lease import (
    SessionLeaseTimeout,
    acquire_session_lease,
    session_lease_path,
)


@pytest.mark.asyncio
async def test_lease_is_exclusive_and_released(tmp_path: Path) -> None:
    async with acquire_session_lease(tmp_path, "identity", timeout_seconds=0.1):
        lock_path = session_lease_path(tmp_path, "identity")
        assert lock_path.exists()
        with pytest.raises(SessionLeaseTimeout):
            async with acquire_session_lease(
                tmp_path,
                "identity",
                timeout_seconds=0.02,
                poll_seconds=0.01,
            ):
                pass
    assert not lock_path.exists()


@pytest.mark.asyncio
async def test_stale_lease_is_reclaimed(tmp_path: Path) -> None:
    lock_path = session_lease_path(tmp_path, "identity")
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("stale", encoding="utf-8")
    old = 1
    lock_path.touch()
    import os

    os.utime(lock_path, (old, old))
    async with acquire_session_lease(
        tmp_path,
        "identity",
        timeout_seconds=0.1,
        stale_after_seconds=1,
        poll_seconds=0.01,
    ):
        assert lock_path.exists()


@pytest.mark.asyncio
async def test_different_identities_do_not_block_each_other(tmp_path: Path) -> None:
    async with acquire_session_lease(tmp_path, "one", timeout_seconds=0.1):
        async with acquire_session_lease(tmp_path, "two", timeout_seconds=0.1):
            await asyncio.sleep(0)
            assert session_lease_path(tmp_path, "one").exists()
            assert session_lease_path(tmp_path, "two").exists()