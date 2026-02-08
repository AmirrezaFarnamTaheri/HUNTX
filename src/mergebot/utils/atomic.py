import os
import shutil
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

def atomic_write(target_path: Union[str, Path], data: Union[str, bytes], mode: str = "wb") -> None:
    """
    Writes data to a temporary file and then renames it to the target path.
    Ensures that the write operation is atomic.

    Args:
        target_path: The final path where the file should be stored.
        data: The content to write (bytes or str).
        mode: The file mode ('w', 'wb', etc.). Defaults to 'wb'.
    """
    path = Path(target_path)
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create a temp file in the same directory to ensure atomic move is possible
    # We append a random suffix or just .tmp. Using .tmp might have concurrency issues
    # if multiple threads write to same file (which shouldn't happen usually).
    # To be safer, let's use a random suffix?
    # But for now, simple .tmp is what RawStore was using partially.
    # Let's use .tmp.<pid> to be safer?
    # Actually, standard practice is strict usage.
    # Let's stick to .tmp for now as it's simple and consistent with previous code.

    tmp_path = path.with_name(path.name + ".tmp")

    # Auto-adjust mode based on data type if necessary, but prefer explicit mode.
    if isinstance(data, str) and "b" in mode:
        data = data.encode("utf-8")

    try:
        with open(tmp_path, mode) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename (replace=True is default on POSIX for os.rename/Path.rename)
        tmp_path.rename(path)

    except Exception as e:
        logger.error(f"Failed to atomically write to {path}: {e}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
