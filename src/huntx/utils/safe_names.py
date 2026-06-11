import re
from pathlib import PurePosixPath


_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_component(value: str, *, default: str = "x", max_len: int = 120) -> str:
    """
    Sanitize a string for safe use inside filenames (single path segment).
    - Removes path separators and weird characters
    - Collapses unsafe chars to '_'
    - Ensures non-empty, length-bounded
    """
    if not isinstance(value, str):
        value = str(value)

    # Drop directory components first (defense in depth).
    value = value.replace("\\", "/")
    value = value.split("/")[-1]

    value = value.strip()
    value = _SAFE_CHARS_RE.sub("_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._-")

    if not value:
        value = default

    if len(value) > max_len:
        value = value[:max_len]

    return value


def safe_zip_entry_name(original_name: str, *, default: str = "file.bin") -> str:
    """
    Return a safe ZIP entry name (flat basename only) to prevent zip-slip.
    """
    if not isinstance(original_name, str):
        original_name = str(original_name)

    # Force posix semantics for ZIP, then take basename.
    original_name = original_name.replace("\\", "/")
    base = PurePosixPath(original_name).name
    base = safe_component(base, default=default, max_len=200)

    # ZIP tools can treat empty names strangely; ensure we always have something.
    return base or default

