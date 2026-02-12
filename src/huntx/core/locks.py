import sys
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def acquire_lock(lock_file: Path):
    """Cross-platform exclusive file lock (POSIX fcntl / Windows msvcrt)."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_file, "w")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except (IOError, OSError):
        print("Another instance is running. Exiting.")
        sys.exit(0)
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.lockf(f, fcntl.LOCK_UN)
        except OSError as e:
            logger.debug(f"Failed to release lock {lock_file}: {e}")
        f.close()
