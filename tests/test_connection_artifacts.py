"""Sanitized multi-format Telegram message parsing regressions."""
import base64
import json

from huntx.formats.connection_artifacts import (
    ConnectionArtifactsHandler,
    extract_connection_artifacts,
)


def _profile(kind):
    server = {"domain": "edge.example.org"}
    profile = {"id": "fixture", "name": "fixture", "server": server}
    if kind == "soar":
        server["public_key"] = base64.b64encode(b"s" * 32).decode()
        profile["soarSettings"] = {"transport": "auto", "maxStreams": 128}
    else:
        profile["engine"] = kind
        server.update(encryption_key="ab" * 32, encryption_method=5)
    document = {"schema": "whitedns.profile", "version": 1, "profile": profile}
    return kind + "://" + base64.b64encode(json.dumps(document).encode()).decode()


def test_whitedns_profiles_are_typed_and_lossless():
    links = [_profile(kind) for kind in ("soar", "cottendns", "masterdns")]
    text = ("Quote Quote " + links[0] + " " + links[1].replace("://", r"\://") + "\n" + links[2])
    records = ConnectionArtifactsHandler().parse(text.encode(), {})
    assert [r["data"]["protocol"] for r in records] == ["soar", "cottendns", "masterdns"]
    assert [r["data"]["raw"] for r in records] == links
    assert all(r["data"]["decoded"]["profile"]["server"]["domain"] == "edge.example.org" for r in records)


def test_invalid_whitedns_payload_is_not_accepted():
    fake = {"schema": "wrong", "version": 1,
            "profile": {"server": {"domain": "edge.example.org"}}}
    value = "soar://" + base64.b64encode(json.dumps(fake).encode()).decode()
    assert extract_connection_artifacts(value) == []


def test_exported_mixed_telegram_formats_are_preserved_and_not_misconverted():
    message = r"""
Quote Quote wireguard://dGVzdA==\@198.51.100.2:51820?publickey=dGVzdA%3D#Example
Quote Quote [Interface] \
PrivateKey = cHJpdmF0ZQ== \
Address = 172.16.0.2/32 \
I1 = \<r 2\>\<b 0x010203\> \
[Peer] \
PublicKey = cHVibGlj \
Endpoint = 198.51.100.2:51820 \
AllowedIPs = 0.0.0.0/0, ::/0 \
Tap the config to copy it
**Master DNS:**\
domain: `dns.example.org`\
private key: `00112233445566778899aabbccddeeff`\
webtunnel [2001:db8::1]:443 0123456789ABCDEF0123456789ABCDEF01234567 url=[https://bridge.example.org/path](https://bridge.example.org/path) webtunnel 198.51.100.3:443 0123456789ABCDEF0123456789ABCDEF01234567 url=https://bridge.example.org/path
[https://t.me/proxy?server=198.51.100.3&port=8443&secret=dd00112233445566778899aabbccddeeff](https://t.me/proxy?server=198.51.100.3\&port=8443\&secret=dd00112233445566778899aabbccddeeff)
`lantern://private-server?ip=example.org&port=12080&token=fixture-token`
"""
    records = extract_connection_artifacts(message)
    protocols = [r["protocol"] for r in records]
    assert protocols.count("wireguard") == 2
    assert protocols.count("masterdns_manual") == 1
    assert protocols.count("tor_webtunnel") == 2
    assert protocols.count("mtproto") == 1
    assert protocols.count("lantern") == 1
    assert all(not item["client_exportable"] for item in records)
    block = next(r for r in records if r["protocol"] == "wireguard" and "interface" in r["decoded"])
    assert block["decoded"]["interface"]["I1"] == "<r 2><b 0x010203>"
    assert block["decoded"]["peer"]["Endpoint"] == "198.51.100.2:51820"
    link = next(r for r in records if r["protocol"] == "wireguard" and r["encoding"] == "share_uri")
    assert r"\@" not in link["raw"]


def test_false_positives_in_telegram_prose_are_not_configs():
    assert extract_connection_artifacts("Read https://t.me/s/WhiteDNS for news; soar://invalid") == []


def test_parser_rejects_unbounded_inputs_without_allocating_typed_records():
    handler = ConnectionArtifactsHandler()
    raw = b"soar://invalid\n" * 400000
    try:
        handler.parse(raw, {})
        assert False, "oversized input must be rejected"
    except ValueError:
        pass
