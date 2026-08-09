# src/huntx/formats/common/__init__.py
"""Common utilities shared across format handlers.

Public API:
    b64_decode     — URL-safe base64 decoder with auto-padding
    hash_string    — LRU-cached SHA-256 of a UTF-8 string
    hash_bytes     — SHA-256 of raw bytes (not cached)
    normalize_text — LRU-cached NFKC normalization + strip
"""
