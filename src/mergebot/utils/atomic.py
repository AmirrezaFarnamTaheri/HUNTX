import os
import threading
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def atomic_write(target_path: Union[str, Path], data: Union[str, bytes], mode: str = "wb") -> None:
    """Write data atomically via temp-file + os.replace (works on POSIX & Windows)."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Unique tmp suffix avoids collisions from concurrent threads / processes
    suffix = f".tmp.{os.getpid()}.{threading.get_ident()}"
    tmp_path = path.with_name(path.name + suffix)

    if isinstance(data, str) and "b" in mode:
        data = data.encode("utf-8")

    try:
        with open(tmp_path, mode) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # os.replace is atomic and overwrites on both POSIX and Windows
        os.replace(str(tmp_path), str(path))

    except Exception as e:
        logger.error(f"Failed to atomically write to {path}: {e}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
