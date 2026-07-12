from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator


class SessionLeaseTimeout(RuntimeError):
    pass


def session_lease_path(root: Path, session_identity: str) -> Path:
    digest = hashlib.sha256(session_identity.encode("utf-8")).hexdigest()[:24]
    return root / "session-leases" / f"{digest}.lock"


def _try_create(path: Path, owner: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        payload = json.dumps(owner, sort_keys=True).encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _remove_if_stale(path: Path, stale_after_seconds: float, now: float) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    if now - stat.st_mtime <= stale_after_seconds:
        return False
    stale_path = path.with_name(f"{path.name}.stale-{int(now)}-{os.getpid()}")
    try:
        os.replace(path, stale_path)
    except FileNotFoundError:
        return False
    stale_path.unlink(missing_ok=True)
    return True


@asynccontextmanager
async def acquire_session_lease(
    root: Path,
    session_identity: str,
    *,
    timeout_seconds: float = 30.0,
    stale_after_seconds: float = 4 * 60 * 60,
    poll_seconds: float = 0.2,
) -> AsyncIterator[Path]:
    path = session_lease_path(root, session_identity)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    owner = {
        "pid": os.getpid(),
        "created_at": time.time(),
        "session_sha256": hashlib.sha256(session_identity.encode("utf-8")).hexdigest(),
    }
    while True:
        if _try_create(path, owner):
            break
        _remove_if_stale(path, stale_after_seconds, time.time())
        if time.monotonic() >= deadline:
            raise SessionLeaseTimeout(
                f"Timed out waiting for exclusive Telegram session ownership: {path.name}"
            )
        await asyncio.sleep(max(0.01, poll_seconds))
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)