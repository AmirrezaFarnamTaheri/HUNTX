# src/huntx/formats/common/b64.py
"""Shared URL-safe base64 decoder used across format handlers.

Single source of truth replacing three private copies in:
  - formats/npvt.py (_b64_decode_safe)
  - pipeline/build.py (BuildPipeline._b64_decode)
  - formats/proxy_uri_validator.py (_decode_base64_text)
"""
from __future__ import annotations

import base64


def b64_decode(value: str) -> str:
    """Decode URL-safe or standard base64 with automatic padding.

    Args:
        value: base64-encoded string (URL-safe or standard, with or without padding).

    Returns:
        Decoded UTF-8 string.

    Raises:
        binascii.Error: if *value* is not valid base64.
        UnicodeDecodeError: if the decoded bytes are not valid UTF-8.
    """
    normalized = value.replace("-", "+").replace("_", "/")
    padding = (4 - len(normalized) % 4) % 4
    normalized += "=" * padding
    decoded = base64.b64decode(normalized, validate=True)
    return decoded.decode("utf-8")


def b64_decode_bytes(value: str) -> bytes:
    """Decode URL-safe or standard base64 with automatic padding, as bytes.

    The byte-level counterpart of :func:`b64_decode`. It exists so callers
    that re-encode a decoded payload do not have to round-trip it through a
    UTF-8 decode, which would fail on payloads that are not valid UTF-8.

    Raises:
        binascii.Error: if *value* is not valid base64.
    """
    normalized = value.replace("-", "+").replace("_", "/")
    padding = (4 - len(normalized) % 4) % 4
    normalized += "=" * padding
    return base64.b64decode(normalized, validate=True)
