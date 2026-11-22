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


def test_typed_artifacts_cannot_be_published_as_generic_proxy_feeds():
    from huntx.formats.registry import FormatRegistry

    registry = FormatRegistry()
    handler = ConnectionArtifactsHandler()
    registry.register(handler)
    assert registry.get("connection_artifacts") is handler
    assert not registry.can_build("connection_artifacts")
    try:
        handler.build([])
        assert False, "raw credential-bearing artifacts must not be published"
    except NotImplementedError:
        pass


def test_telegram_post_with_four_encrypted_slipnet_links_retains_all_ciphertext():
    from unittest.mock import patch

    from huntx.formats.common.crypto import MissingSecretError
    from huntx.formats.slipnet import SlipNetHandler

    # Four harmless synthetic ciphertexts, not copied from user credentials.
    blobs = [
        base64.b64encode(b"\x01" + bytes([n]) * 44).decode("ascii")
        for n in range(1, 5)
    ]
    links = ["slipnet-enc://" + blob for blob in blobs]
    post = "Slipnet SSH configurations\n" + "\n\n".join(links)
    with patch(
        "huntx.formats.slipnet.decrypt_slipnet_link",
        side_effect=MissingSecretError("operator key not configured"),
    ):
        records = SlipNetHandler().parse(post.encode("utf-8"), {})
    assert len(records) == 4
    assert [record["data"]["line"] for record in records] == links
    assert all("decrypted" not in record["data"] for record in records)


def test_full_synthetic_telegram_message_recovers_all_32_expected_artifacts():
    from collections import Counter

    parts = []
    for kind, how_many in (("soar", 4), ("cottendns", 2), ("masterdns", 2)):
        for n in range(how_many):
            server = {"domain": f"public-{kind}-{n}.example.org"}
            profile = {"id": f"{kind}-{n}", "name": "Synthetic public profile", "server": server}
            if kind == "soar":
                server["public_key"] = base64.b64encode(b"s" * 32).decode("ascii")
                profile["soarSettings"] = {"transport": "auto"}
            else:
                profile["engine"] = kind
                server["encryption_key"] = "ab" * 32
                server["encryption_method"] = 5
            payload = {"schema": "whitedns.profile", "version": 1, "profile": profile}
            link = kind + "://" + base64.b64encode(json.dumps(payload).encode()).decode()
            parts.append("Quote Quote " + (link.replace("://", r"\://") if n % 2 else link))

    for n in range(3):
        parts.append(f"Quote Quote wireguard://cHJpdmF0ZQ==@198.51.100.{n + 10}:51820?publickey=cHVibGlj#WG{n}")
    for n in range(12):
        parts.append(
            "Quote Quote [Interface]\n"
            "PrivateKey = cHJpdmF0ZQ==\n"
            f"Address = 172.16.0.{n + 2}/32\n"
            f"I1 = \\<r 2\\>\\<b 0x{n:08x}\\>\n"
            "[Peer]\n"
            "PublicKey = cHVibGlj\n"
            "AllowedIPs = 0.0.0.0/0, ::/0\n"
            f"Endpoint = 198.51.100.{n + 10}:51820\n"
            "PersistentKeepalive = 25\n"
            "Tap the config to copy it\n"
        )
    for label, n in (("Master DNS", 1), ("Storm DNS", 2),
                     ("Cotten DNS", 3), ("Soar", 4), ("Soar 2.2", 5)):
        parts.append(
            f"**{label}:**\n"
            f"domain: domain{n}.example.org\n"
            "private key: 00112233445566778899aabbccddeeff\n"
            "\n"
        )
    fingerprint = "0123456789ABCDEF0123456789ABCDEF01234567"
    parts.extend([
        f"webtunnel [2001:db8::1]:443 {fingerprint} url=https://bridge.example.org/path",
        f"webtunnel 198.51.100.4:443 {fingerprint} url=https://bridge.example.org/path",
        "https://t.me/proxy?server=198.51.100.9&port=8443"
        "&secret=dd00112233445566778899aabbccddeeff",
        "lantern://private-server?ip=example.org&port=12080&token=synthetic-token",
    ])
    records = extract_connection_artifacts("\n\n".join(parts))
    counts = Counter(item["protocol"] for item in records)
    assert len(records) == 32
    assert counts["wireguard"] == 15
    assert counts["soar"] == 4
    assert counts["cottendns"] == 2
    assert counts["masterdns"] == 2
    assert counts["tor_webtunnel"] == 2
    assert counts["mtproto"] == 1
    assert counts["lantern"] == 1
    assert counts["masterdns_manual"] == 1
    assert counts["stormdns_manual"] == 1
    assert counts["cottendns_manual"] == 1
    assert counts["soar_manual"] == 1
    assert counts["soar22_manual"] == 1


def test_multipeer_wireguard_keeps_each_peer_and_original_fields():
    """A second [Peer] must not silently overwrite the first peer."""
    message = """[Interface]
# synthetic interface comment
PrivateKey = cHJpdmF0ZQ==
Address = 192.0.2.10/32

[Peer]
# synthetic first peer
PublicKey = cHVibGljMQ==
AllowedIPs = 10.0.0.0/8
AllowedIPs = 192.168.0.0/16
Endpoint = peer-one.example.org:51820

[Peer]
PublicKey = cHVibGljMg==
Endpoint = peer-two.example.org:51820
AllowedIPs = 0.0.0.0/0
"""
    records = extract_connection_artifacts(message)
    assert len(records) == 1
    record = records[0]
    assert record["protocol"] == "wireguard"
    assert record["encoding"] == "ini"
    assert record["client_exportable"] is False
    assert len(record["decoded"]["peers"]) == 2
    assert record["decoded"]["peer"]["Endpoint"] == "peer-one.example.org:51820"
    assert record["decoded"]["peers"][1]["Endpoint"] == "peer-two.example.org:51820"
    assert "# synthetic interface comment" in record["raw"]
    assert "# synthetic first peer" in record["raw"]
    assert record["raw"].count("AllowedIPs =") == 3
    assert record["raw"].count("[Peer]") == 2


def test_partial_multipeer_wireguard_is_not_accepted_as_complete():
    message = """[Interface]
PrivateKey = cHJpdmF0ZQ==
[Peer]
PublicKey = cHVibGljMQ==
Endpoint = peer-one.example.org:51820
[Peer]
PublicKey = cHVibGljMg==
"""
    assert extract_connection_artifacts(message) == []
