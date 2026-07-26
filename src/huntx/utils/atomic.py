import logging
import os
import stat
import threading
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]
Payload = Union[str, bytes]
_COMPARE_CHUNK_SIZE = 1024 * 1024


def _coerce_payload(data: Payload, mode: str) -> Payload:
    if isinstance(data, str) and "b" in mode:
        return data.encode("utf-8")
    if isinstance(data, bytes) and "b" not in mode:
        return data.decode("utf-8")
    return data


def _content_matches(path: Path, data: Payload, mode: str) -> bool:
    """Return True when *path* already contains *data* without loading it twice."""
    if not path.is_file():
        return False

    payload = _coerce_payload(data, mode)
    try:
        if "b" not in mode:
            return path.read_text(encoding="utf-8") == payload

        assert isinstance(payload, bytes)
        if path.stat().st_size != len(payload):
            return False

        view = memoryview(payload)
        offset = 0
        with path.open("rb") as stream:
            while offset < len(payload):
                chunk = stream.read(_COMPARE_CHUNK_SIZE)
                if not chunk or chunk != view[offset : offset + len(chunk)]:
                    return False
                offset += len(chunk)
            return stream.read(1) == b""
    except OSError:
        return False


def atomic_write(target_path: PathLike, data: Payload, mode: str = "wb") -> None:
    """Write data atomically via temp-file + os.replace (POSIX and Windows).

    Text modes always encode as UTF-8: relying on the platform default
    encoding would corrupt or reject non-ASCII payloads on non-UTF-8 locales,
    and ``_content_matches`` already compares text content as UTF-8.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _coerce_payload(data, mode)

    suffix = f".tmp.{os.getpid()}.{threading.get_ident()}"
    tmp_path = path.with_name(path.name + suffix)

    # Preserve an existing target's permission bits. The temp file is created
    # with the current umask-derived mode, so without this, os.replace would
    # silently narrow (or widen) the file's permissions on every atomic write.
    try:
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        existing_mode = None

    encoding = None if "b" in mode else "utf-8"
    try:
        with open(tmp_path, mode, encoding=encoding) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if existing_mode is not None:
            os.chmod(tmp_path, existing_mode)
        os.replace(str(tmp_path), str(path))
    except Exception as exc:
        logger.error("Failed to atomically write to %s: %s", path, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_if_changed(target_path: PathLike, data: Payload, mode: str = "wb") -> bool:
    """Atomically write only when bytes differ; return whether a write occurred."""
    path = Path(target_path)
    if _content_matches(path, data, mode):
        return False
    atomic_write(path, data, mode=mode)
    return True
