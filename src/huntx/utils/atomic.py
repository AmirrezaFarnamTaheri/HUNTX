import logging
import os
import stat
import tempfile
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


def _payload_bytes(data: Payload, mode: str) -> bytes:
    """Return the exact bytes represented by *data* and *mode*."""
    payload = _coerce_payload(data, mode)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return payload


def _content_matches(path: Path, data: Payload, mode: str) -> bool:
    """Return True when *path* already contains *data* without loading it twice."""
    if not path.is_file():
        return False

    payload = _payload_bytes(data, mode)
    try:
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
    payload = _payload_bytes(data, mode)

    descriptor, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)

    # Preserve an existing target's permission bits. The temp file is created
    # with the current umask-derived mode, so without this, os.replace would
    # silently narrow (or widen) the file's permissions on every atomic write.
    try:
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        existing_mode = None

    try:
        # Always write bytes so text payloads have identical UTF-8/newline
        # representation on POSIX and Windows.
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = -1
        if existing_mode is not None:
            os.chmod(tmp_path, existing_mode)
        os.replace(str(tmp_path), str(path))
        # Persist the directory entry where the platform exposes a directory
        # file descriptor. Windows does not support opening directories this
        # way, so replacement durability there follows os.replace semantics.
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception as exc:
        logger.error("Failed to atomically write to %s: %s", path, exc)
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
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
