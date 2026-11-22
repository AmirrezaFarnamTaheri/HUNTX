"""Hot-path safety and correctness for proxy text normalization."""

from unittest.mock import patch

from huntx.core.router import _contains_proxy_uri, decide_format
from huntx.formats.common.normalize_text import _normalize_unicode, normalize_text


def test_unique_ascii_proxy_credentials_not_retained_in_unicode_cache():
    # Protect the dominant high-cardinality URI path from a process-wide
    # LRU retaining thousands of full plaintext proxy credentials.
    _normalize_unicode.cache_clear()
    for index in range(12000):
        uri = f"vless://test-{index}@edge.example.org:443#node-{index}"
        assert normalize_text(uri) == uri
    assert _normalize_unicode.cache_info().currsize == 0



def test_non_ascii_share_links_are_not_cached_with_plaintext_credentials():
    _normalize_unicode.cache_clear()
    uri = "vless://test-secret@edge.example.org:443#🇸🇬"
    assert normalize_text(uri) == uri
    assert _normalize_unicode.cache_info().currsize == 0


def test_nfkc_unicode_remains_semantically_identical():
    _normalize_unicode.cache_clear()
    assert normalize_text("  ＶＬＥＳＳ：／／Ｕｎｉｃｏｄｅ  ") == "VLESS://Unicode"
    assert normalize_text("  café  ") == "café"
    assert _normalize_unicode.cache_info().currsize == 2
    assert normalize_text("  café  ") == "café"
    assert _normalize_unicode.cache_info().hits >= 1
    assert normalize_text("  vless://fixture@example.org:443  ") == "vless://fixture@example.org:443"


def test_router_without_uri_marker_skips_expensive_proxy_regex():
    with patch("huntx.core.router._AUTH_HTTP_PROXY_RE") as proxy_regex:
        proxy_regex.search.side_effect = AssertionError("should not search ordinary prose")
        assert not _contains_proxy_uri("Forwarded from Telegram: useful connection instructions")
    assert decide_format("message.txt", b"Some public news without URLs") == "opaque_bundle"
    assert decide_format("message.txt", b"Quote Quote vless://secret@example.org:443") == "npvt"
