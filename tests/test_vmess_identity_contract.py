"""Regression tests for the shared VMess identity contract.

A VMess link carries its display remark in the payload's ``ps`` field, so two
links that describe the same proxy under different remarks must collapse onto
one identity. Every layer that decides a proxy's identity -- the parse path,
the state store and the snapshot assembler -- has to agree on that form, or
the same proxy is stored under two different hashes and published twice.
"""
import base64
import json

import pytest

from huntx.formats.common.vmess import (
    canonical_vmess_line,
    decode_vmess_payload,
    vmess_payload_with_remark,
)
from huntx.formats.npvt import add_clean_remark, strip_proxy_remark
from huntx.state.db import _canonicalize_vmess_line


def _encode(payload) -> str:
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode(uri: str) -> dict:
    body = uri.partition("#")[0][8:]
    padded = body + "=" * ((4 - len(body) % 4) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


BASE = {
    "v": "2",
    "add": "vmess.example.invalid",
    "port": "443",
    "id": "00000000-0000-4000-8000-000000000001",
    "aid": "0",
    "net": "ws",
    "type": "none",
}


def test_remark_is_dropped_from_the_canonical_form():
    uri = "vmess://" + _encode({**BASE, "ps": "some channel"})

    canonical = canonical_vmess_line(uri)

    assert canonical is not None
    assert "ps" not in _decode(canonical)
    assert _decode(canonical) == BASE


def test_two_remarks_share_one_identity():
    first = "vmess://" + _encode({**BASE, "ps": "Channel_A"})
    second = "vmess://" + _encode({**BASE, "ps": "Channel_B"})

    assert canonical_vmess_line(first) == canonical_vmess_line(second)


def test_key_order_does_not_change_the_identity():
    first = "vmess://" + _encode({"v": "2", "add": "a.invalid", "port": "443"})
    second = "vmess://" + _encode({"port": "443", "add": "a.invalid", "v": "2"})

    assert canonical_vmess_line(first) == canonical_vmess_line(second)


def test_non_ascii_payload_is_not_escaped():
    """The canonical bytes must match the v10 migration's ``ensure_ascii=False``.

    A canonicalizer that escaped non-ASCII text would hash a non-ASCII proxy
    differently from the migration that re-keys legacy rows, so the record
    would be re-keyed on every upgrade and published twice.
    """
    payload = {**BASE, "ps": "کانال فارسی", "sni": "مثال.ایران"}
    uri = "vmess://" + _encode(payload)

    canonical = canonical_vmess_line(uri)

    assert canonical is not None
    # The escaped form would contain a literal backslash-u sequence.
    assert b"\\u" not in base64.b64decode(canonical[8:])
    assert _decode(canonical)["sni"] == "مثال.ایران"


def test_non_ascii_identity_agrees_with_the_state_store():
    uri = "vmess://" + _encode({**BASE, "ps": "کانال فارسی"})

    assert _canonicalize_vmess_line(uri) == canonical_vmess_line(uri)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        ["a", "b"],
        "just-a-string",
        42,
        3.5,
        True,
        None,
    ],
)
def test_a_payload_that_is_not_an_object_is_not_a_vmess_link(payload):
    """A JSON array, string or number has no ``ps`` field and no identity.

    The old inline canonicalizer called ``obj.pop('ps')`` on whatever
    ``json.loads`` returned, which raised ``AttributeError`` for every
    non-object payload.
    """
    uri = "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode("ascii")

    assert canonical_vmess_line(uri) is None
    assert decode_vmess_payload(uri) is None
    assert _canonicalize_vmess_line(uri) is None
    # The original URI is preserved rather than rewritten or crashed on.
    assert strip_proxy_remark(uri) == uri
    assert add_clean_remark(uri, {}) == uri


def test_undecodable_payload_is_preserved_not_rewritten():
    uri = "vmess://not-valid-base64!"

    assert canonical_vmess_line(uri) is None
    assert strip_proxy_remark(uri) == uri
    assert add_clean_remark(uri, {}) == uri


def test_the_state_store_and_the_parse_path_agree():
    uri = "vmess://" + _encode({**BASE, "ps": "Channel"})

    assert _canonicalize_vmess_line(uri) == strip_proxy_remark(uri)


def test_adding_a_remark_removes_the_obsolete_url_fragment():
    uri = "vmess://" + _encode({**BASE, "ps": "old"}) + "#%73ource-1"

    remarked = vmess_payload_with_remark(uri, "vmess-1")

    assert remarked is not None
    assert "#" not in remarked
    assert _decode(remarked)["ps"] == "vmess-1"


def test_adding_a_remark_to_a_non_object_payload_preserves_the_uri():
    uri = "vmess://" + base64.b64encode(b"[1,2,3]").decode("ascii")

    assert vmess_payload_with_remark(uri, "vmess-1") is None
    assert add_clean_remark(uri, {}) == uri
