# tests/perf/test_router_bench.py
"""
Micro-benchmarks for normalize_text and hash_string LRU cache correctness.
Run with: pytest tests/perf/ -m perf -v
Not included in default CI run (-m not perf).
"""
import pytest
from huntx.formats.common.hashing import hash_string
from huntx.formats.common.normalize_text import normalize_text

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
def test_normalize_text_is_lru_cached():
    """After first call, repeated calls must register as cache hits."""
    normalize_text.cache_clear()
    first = normalize_text(SAMPLE_URI)
    for _ in range(ITERATIONS):
        assert normalize_text(SAMPLE_URI) == first
    info = normalize_text.cache_info()
    assert info.hits >= ITERATIONS - 1, (
        f"Expected {ITERATIONS - 1} cache hits, got {info.hits}."
    )
