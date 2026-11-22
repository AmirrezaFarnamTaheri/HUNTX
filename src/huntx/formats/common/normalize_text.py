import unicodedata
from functools import lru_cache


@lru_cache(maxsize=8192)
def _normalize_unicode(text: str) -> str:
    """Cache uncommon Unicode NFKC normalization, never plaintext ASCII URIs."""
    return unicodedata.normalize("NFKC", text).strip()


def normalize_text(text: str) -> str:
    """Normalize text without retaining high-cardinality ASCII proxy secrets.

    Most subscription lines are unique ASCII URIs. Retaining their plaintext
    in a process-wide LRU adds overhead, memory pressure and credential
    lifetime for no useful cache hits. Unicode still benefits from caching.
    """
    if not text:
        return ""
    if text.isascii():
        return text.strip()
    # Unicode comments sometimes appear on otherwise ASCII proxy URIs.
    # Avoid caching credential-bearing/large payloads even in that case.
    if "://" in text or "@" in text or "=" in text or len(text) > 128:
        return unicodedata.normalize("NFKC", text).strip()
    return _normalize_unicode(text)
