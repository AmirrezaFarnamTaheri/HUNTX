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


# Upper bound on how long a stale-lease reclamation can legitimately take.
# Reclamation is a few filesystem syscalls (microseconds); a ``.reap`` marker
# older than this can only mean the reaping process died mid-operation, so it
# is safe to force-remove and retry. Kept far longer than any real reap to
# guarantee we never yank a marker out from under a live reaper.
_REAP_LOCK_TTL_SECONDS = 60.0


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


def _is_stale(path: Path, stale_after_seconds: float, now: float) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    return (now - stat.st_mtime) > stale_after_seconds


def _acquire_reap_lock(reap_path: Path) -> bool:
    """Acquire the exclusive reap marker, force-removing a crashed one.

    Only the holder of this marker may reclaim a stale lease, which serializes
    reapers so at most one removes the stale file at a time. Returns True if
    this caller now owns the marker.
    """
    try:
        descriptor = os.open(reap_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            age = time.time() - reap_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age <= _REAP_LOCK_TTL_SECONDS:
            return False  # another reaper is active; do not disturb it
        # The prior reaper is long dead: reclaim its marker, then retry once.
        try:
            os.unlink(reap_path)
        except FileNotFoundError:
            pass
        try:
            descriptor = os.open(reap_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False  # lost the race to another reaper — let them proceed
    os.close(descriptor)
    return True


def _remove_if_stale(path: Path, stale_after_seconds: float, now: float) -> bool:
    """Reclaim ``path`` iff it is a genuinely stale lease.

    Reclamation is guarded by an ``O_EXCL`` reap marker so that only one
    process removes the stale file. Because a fresh lease can only be created
    while ``path`` does *not* exist (holders use ``O_EXCL``), the stale file
    is guaranteed to remain the same inode from the re-check under the marker
    through ``os.replace`` — closing the race where a late ``os.replace`` from
    one waiter could clobber a live lease freshly created by another.
    """
    if not _is_stale(path, stale_after_seconds, now):
        return False

    reap_path = path.with_name(f"{path.name}.reap")
    if not _acquire_reap_lock(reap_path):
        return False
    try:
        # Re-verify under the reap marker with a fresh clock reading. If the
        # file vanished or is no longer stale (i.e. was reclaimed and a fresh
        # lease took its place after the marker was released), do nothing.
        if not _is_stale(path, stale_after_seconds, time.time()):
            return False
        stale_path = path.with_name(f"{path.name}.stale-{int(now)}-{os.getpid()}")
        try:
            os.replace(path, stale_path)
        except FileNotFoundError:
            return False
        Path(stale_path).unlink(missing_ok=True)
        return True
    finally:
        try:
            os.unlink(reap_path)
        except FileNotFoundError:
            pass


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
