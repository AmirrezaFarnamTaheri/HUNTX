import unicodedata
from functools import lru_cache


@lru_cache(maxsize=8192)
def normalize_text(text: str) -> str:
    """
    Normalizes text to NFKC, strips whitespace, handles unified newlines.
    Cached for fast repeated lookups across subscription files.
    """
    if not text:
        return ""
    # NFKC normalization for compatibility
    text = unicodedata.normalize("NFKC", text)
    # Strip whitespace
    text = text.strip()
    return text
