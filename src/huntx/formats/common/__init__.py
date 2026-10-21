# src/huntx/formats/common/__init__.py
"""Common utilities shared across format handlers.

The submodules are imported explicitly by their users; this package does not
re-export them, so that importing ``huntx.formats.common`` never pulls in the
hashing or normalization machinery a caller does not use.

Submodules:
    b64         — URL-safe base64 decoding (``b64_decode``, ``b64_decode_bytes``)
    hashing     — SHA-256 helpers (``hash_string``, ``hash_bytes``)
    normalize_text — NFKC normalization and whitespace stripping
    vmess       — the shared VMess identity contract
                  (``canonical_vmess_line``, ``decode_vmess_payload``,
                  ``vmess_payload_with_remark``)
"""
