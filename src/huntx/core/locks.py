import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


@contextmanager
def acquire_lock(lock_file: Path) -> Iterator[None]:
    """Acquire one non-blocking cross-platform exclusive file lock.

    Only lock-acquisition failures are translated to the operator-facing
    "another instance" error. Exceptions raised by the protected operation are
    deliberately allowed to propagate unchanged so the real failure cause is
    never hidden by the lock wrapper.
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_file, "a+")
    locked = False
    try:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another instance of HuntX is already running.") from exc

        locked = True
        yield
    finally:
        if locked:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.lockf(handle, fcntl.LOCK_UN)
            except OSError as exc:
                logger.debug("Failed to release lock %s: %s", lock_file, exc)
        handle.close()
