import fcntl
import os
import sys
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def acquire_lock(lock_file: Path):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_file, "w")
    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except IOError:
        print("Another instance is running. Exiting.")
        sys.exit(0)
    finally:
        try:
            fcntl.lockf(f, fcntl.LOCK_UN)
        except:
            pass
        f.close()
