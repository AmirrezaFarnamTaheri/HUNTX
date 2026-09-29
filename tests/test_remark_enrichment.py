"""The published remark must be identifiable, deterministic, and unique.

A feed of ~1700 nodes named ``vless-1`` .. ``vless-1700`` cannot be navigated.
The information needed to tell them apart is already in the URI, so the remark
carries the transport and security that actually apply - and nothing that is
true of every node of that type.
"""

from __future__ import annotations

import base64
import collections
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huntx.formats.npvt import (  # noqa: E402
    NpvtHandler,
    add_clean_remark,
    remark_qualifier,
)

REALITY_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
UUID = "11111111-2222-3333-4444-555555555555"


def _remark(uri: str, counter: dict | None = None) -> str:
    counter = {} if counter is None else counter
    return add_clean_remark(uri, counter).rsplit("#", 1)[-1]


def _vmess(ps: str) -> str:
    # A public hostname, not a documentation IP: _valid_host rejects private and
    # reserved addresses, so 198.51.100.0/24 never reaches the builder.
    payload = base64.b64encode(
        json.dumps({"v": "2", "ps": ps, "add": "node.example.com", "port": "443", "id": UUID}).encode()
    ).decode()
    return f"vmess://{payload}"


# ----------------------------------------------------------------- qualifiers
@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (f"vless://{UUID}@node1.example.com:443?security=reality&pbk={REALITY_KEY}&sid=ab12&sni=c.example#n", "reality"),
        (f"vless://{UUID}@node1.example.com:443?security=tls&sni=c.example#n", "tls"),
        (f"vless://{UUID}@node1.example.com:443?security=tls&type=ws&host=h.example&path=%2F#n", "ws-tls"),
        (f"vless://{UUID}@node1.example.com:443?type=grpc&serviceName=g#n", "grpc"),
        (f"vless://{UUID}@node1.example.com:443?security=tls&type=httpupgrade#n", "httpupgrade-tls"),
        (f"vless://{UUID}@node1.example.com:443#n", ""),
        # Trojan, Hysteria2, AnyTLS and TUIC are TLS by design; naming it would
        # put the same word on every node of that type.
        ("trojan://pw@node1.example.com:443#n", ""),
        ("trojan://pw@node1.example.com:443?sni=c.example#n", ""),
        ("hysteria2://pw@node1.example.com:443#n", ""),
        ("anytls://pw@node1.example.com:443#n", ""),
        # A transport is still named even on a TLS-implying protocol, because
        # that is the part which does distinguish its nodes.
        ("trojan://pw@node1.example.com:443?type=ws&path=%2F#n", "ws"),
        # Plain TCP adds nothing, so it is never named.
        (f"vless://{UUID}@node1.example.com:443?type=tcp#n", ""),
        ("garbage", ""),
    ],
)
def test_remark_qualifier_names_only_what_distinguishes(uri, expected):
    assert remark_qualifier(uri) == expected


# --------------------------------------------------------------- the remark
def test_a_reality_node_reads_differently_from_a_plain_one():
    reality = f"vless://{UUID}@node1.example.com:443?security=reality&pbk={REALITY_KEY}&sid=ab12&sni=c.example#n"
    plain = f"vless://{UUID}@node2.example.com:443#n"
    counter: dict = {}
    assert _remark(reality, counter) == "vless-reality-1"
    assert _remark(plain, counter) == "vless-2"


def test_numbering_stays_per_scheme():
    counter: dict = {}
    first = f"vless://{UUID}@node1.example.com:443?security=reality&pbk={REALITY_KEY}&sid=a&sni=c#a"
    second = "trojan://pw@node2.example.com:443#b"
    third = f"vless://{UUID}@node3.example.com:443?security=reality&pbk={REALITY_KEY}&sid=a&sni=c#c"
    assert _remark(first, counter) == "vless-reality-1"
    assert _remark(second, counter) == "trojan-1"
    assert _remark(third, counter) == "vless-reality-2"


def test_the_remark_is_deterministic():
    uri = f"vless://{UUID}@node1.example.com:443?security=tls&type=ws&path=%2F#n"
    assert _remark(uri) == _remark(uri)


def test_a_vmess_remark_lives_in_the_payload():
    """VMess carries its name in ``ps``, not in the URI fragment."""
    handler = NpvtHandler()
    built = handler.build(handler.parse(_vmess("upstream-name").encode(), {})).decode()
    payload = built.strip().split("vmess://", 1)[1].split("#", 1)[0]
    ps = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))["ps"]
    assert ps == "vmess-ws-1" or ps.startswith("vmess")


def test_the_built_feed_has_no_duplicate_remarks():
    handler = NpvtHandler()
    feed = "\n".join([
        f"vless://{UUID}@node{i}:443?security=reality&pbk={REALITY_KEY}&sid=a&sni=c#a{i}" for i in range(1, 6)
    ] + [
        f"vless://{UUID}@node{i}:443?security=tls&type=ws&path=%2F#w{i}" for i in range(10, 14)
    ] + [f"vless://{UUID}@node{i}:443#p{i}" for i in range(20, 24)]
    ) + "\n"
    built = handler.build(handler.parse(feed.encode(), {})).decode()
    tags = [line.rsplit("#", 1)[-1] for line in built.splitlines() if line.strip()]
    assert len(tags) == len(set(tags))
    shapes = collections.Counter(t.rsplit("-", 1)[0] for t in tags)
    assert set(shapes) == {"vless-reality", "vless-ws-tls", "vless"}


# ------------------------------------------------------------- the real feed
def test_the_production_feed_becomes_navigable():
    """The point of the change: many distinct shapes, not one flat list."""
    feed_path = ROOT / "outputs" / "all_sources.npvt"
    if not feed_path.exists():
        pytest.skip("no local production snapshot to analyse")
    handler = NpvtHandler()
    raw = feed_path.read_bytes()
    built = handler.build(handler.parse(raw, {})).decode("utf-8")
    tags = [line.rsplit("#", 1)[-1] for line in built.splitlines() if line.strip()]
    tags = [t for t in tags if not t.startswith("vmess://")]

    assert len(tags) == len(set(tags)), "remarks must be unique"
    shapes = {t.rsplit("-", 1)[0] for t in tags}
    assert len(shapes) >= 8, f"remark shapes barely differentiated: {sorted(shapes)}"
    # A rebuild must not renumber anything.
    again = handler.build(handler.parse(raw, {})).decode("utf-8")
    assert again == built
