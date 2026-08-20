from __future__ import annotations

from .npvt import NpvtHandler


class NpvtSubHandler(NpvtHandler):
    """NapsternetV subscription handler using the canonical proxy URI contract.

    ``npvt`` and ``npvtsub`` carry the same proxy URI families. Keeping a
    second parser previously let malformed prefixed URIs bypass the
    protocol-aware validator and caused support drift as new schemes were
    added. The subscription variant now intentionally shares parsing,
    validation, canonicalization, deduplication, base64 decoding, and build
    behavior with ``NpvtHandler``; only its format identity differs.
    """

    @property
    def format_id(self) -> str:
        return "npvtsub"
