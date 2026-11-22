# tests/perf/test_router_bench.py
"""
Micro-benchmarks for ASCII URI normalization and hash_string LRU caching.
Run with: pytest tests/perf/ -m perf -v
Not included in default CI run (-m not perf).
"""
import pytest
from huntx.formats.common.hashing import hash_string
from huntx.formats.common.normalize_text import _normalize_unicode, normalize_text

SAMPLE_URI = "vless://abc123@192.0.2.1:443?security=tls&sni=example.com#tag"
ITERATIONS = 10_000


@pytest.mark.perf
def test_hash_string_is_lru_cached():
    """After first call, repeated calls must register as cache hits."""
    hash_string.cache_clear()
    first = hash_string(SAMPLE_URI)
    for _ in range(ITERATIONS):
        assert hash_string(SAMPLE_URI) == first
    info = hash_string.cache_info()
    assert info.hits >= ITERATIONS - 1, (
        f"Expected {ITERATIONS - 1} cache hits, got {info.hits}."
    )


@pytest.mark.perf
def test_plaintext_ascii_uri_normalization_has_no_global_lru():
    """Unique ASCII share links should be normalized without caching secrets."""
    _normalize_unicode.cache_clear()
    for i in range(ITERATIONS):
        uri = SAMPLE_URI + f"-{i}"
        assert normalize_text(uri) == uri
    assert _normalize_unicode.cache_info().currsize == 0


@pytest.mark.perf
def test_short_unicode_text_still_benefits_from_caching():
    """Small harmless non-ASCII labels keep their Unicode LRU cache."""
    _normalize_unicode.cache_clear()
    sample = "  Ｃｏｎｆｉｇ  "
    for _ in range(ITERATIONS):
        assert normalize_text(sample) == "Config"
    info = _normalize_unicode.cache_info()
    assert info.hits >= ITERATIONS - 1
