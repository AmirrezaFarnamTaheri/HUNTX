"""Shared VMess canonicalization.

A VMess share link carries its display remark twice: in the JSON payload's
``ps`` field and, optionally, in a URL fragment. Two links that describe the
same proxy under different remarks must therefore collapse onto one identity,
or the same proxy is ingested and published twice.

This module is the single source of truth for that identity. The parse path
(``formats.npvt.strip_proxy_remark``), the state store
(``state.db._canonicalize_vmess_line``) and the snapshot assembler
(``scripts.assemble_generated_snapshot.strip_proxy_remark``) all call it, so
the hash a record is stored under never depends on which of them produced it.
A payload that canonicalized differently on two paths would otherwise be
re-keyed by the schema migration and then re-duplicated by the next parse.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional

from .b64 import b64_decode_bytes

# The JSON encoding used for every canonical VMess payload.
#
# ``ensure_ascii=False`` keeps non-ASCII payload text as UTF-8 instead of
# escaping it to ``\uXXXX``. The schema's v10 migration already re-keys legacy
# records with ``ensure_ascii=False``, so a canonicalizer that escaped
# non-ASCII would produce a different hash for a non-ASCII proxy than the
# migration did: the record would be re-keyed on every upgrade and the same
# proxy would be published twice.
#
# ``sort_keys`` removes the dependence on the key order of the source
# document, and the compact separators keep the encoding byte-identical
# across layers.


def _canonical_json(value: Any) -> str:
    """Encode *value* as canonical VMess JSON.

    One function, so the identity path and the display path cannot drift
    apart in their encoding settings.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def decode_vmess_payload(line: str) -> Optional[dict[str, Any]]:
    """Return the decoded VMess JSON object, or ``None`` when it is not one.

    Decode only the payload: an optional URL fragment is a display remark,
    not connection identity. Standard and URL-safe base64 are both accepted.

    A payload that decodes to a JSON array, string or number is not a VMess
    payload: it has no ``ps`` field to strip and no identity to keep, so it
    is reported as undecodable rather than raising. Callers treat ``None`` as
    "leave this URI alone".
    """
    if not isinstance(line, str) or not line.startswith("vmess://"):
        return None
    body = line.partition("#")[0][8:]
    if not body:
        return None
    try:
        raw = b64_decode_bytes(body)
    except (ValueError, TypeError):
        # binascii.Error is a ValueError subclass.
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        # JSON permits escaped surrogate literals and Python accepts NaN by
        # default. Neither is a portable client payload or canonical UTF-8.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError):
        return None
    return value


def canonical_vmess_line(line: str) -> Optional[str]:
    """Return the canonical VMess URI for *line*, or ``None`` when it is not VMess.

    The canonical form drops the ``ps`` display remark, sorts the JSON keys
    and encodes the payload as UTF-8. Two VMess links that differ only in
    their remark share one canonical form and therefore one identity.
    """
    value = decode_vmess_payload(line)
    if value is None:
        return None
    value.pop("ps", None)
    canonical = _canonical_json(value)
    return "vmess://" + base64.b64encode(canonical.encode("utf-8")).decode("ascii")


def vmess_payload_with_remark(line: str, remark: str) -> Optional[str]:
    """Return *line*'s VMess payload with its ``ps`` field set to *remark*.

    VMess clients read the display name from ``ps``. Remove the old fragment
    so it cannot override the new name or leak the upstream channel label.

    The payload is re-encoded with the same canonical JSON settings the
    identity canonicalizer uses, so a remarked link and its canonical form
    differ only in the ``ps`` field.

    Returns ``None`` when *line* is not a VMess link or its payload is not a
    JSON object, so callers can fall back to the original URI.
    """
    body = line.partition("#")[0]
    value = decode_vmess_payload(body)
    if value is None:
        return None
    value["ps"] = remark
    encoded = _canonical_json(value).encode("utf-8")
    return "vmess://" + base64.b64encode(encoded).decode("ascii")
