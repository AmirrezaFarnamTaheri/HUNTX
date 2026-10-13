"""Evidence-backed endpoint intelligence, with explicit unknowns and privacy."""

import base64
import json
import re

import pytest

from huntx.core.endpoint_intelligence import (
    PrefixIntelligence,
    describe_proxy_endpoint,
)


UUID = "11111111-2222-3333-4444-555555555555"


def snapshot(**overrides):
    original = {
        "schema_version": 1,
        "provider": "offline-fixture",
        "observed_at": 1_800_000_000,
        "expires_at": 1_800_086_400,
        "prefixes": [
            {
                "cidr": "1.1.1.0/24",
                "asn": 13335,
                "as_org": "Example AS",
                "anycast": True,
                "cdn_provider": "Example CDN",
            },
            {
                "cidr": "1.1.1.128/25",
                "asn": 65001,
                "as_org": "Specific AS",
                "country_code": "DE",
                "anycast": False,
            },
        ],
    }
    original.update(overrides)
    return original


def test_endpoint_identity_is_distinct_from_proxy_authentication():
    a = describe_proxy_endpoint(f"vless://{UUID}@EDGE.Example.COM:443?security=tls#US")
    b = describe_proxy_endpoint(
        "vless://aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa@edge.example.com:443?security=tls#DE"
    )
    assert a is not None and b is not None
    assert a["endpoint_id"] == b["endpoint_id"]
    assert a["identity_scope"] == "network_endpoint_not_proxy_credential"
    assert a["host"] == "edge.example.com"
    assert a["port"] == 443
    assert a["host_kind"] == "dns_name"
    assert a["geo"]["status"] == "unresolved_hostname"
    assert a["geo"]["country_code"] is None
    assert a["asn"] is None and a["cdn_provider"] is None
    assert "US" not in json.dumps(a)
    assert "DE" not in json.dumps(b)
    assert UUID not in json.dumps(a)


def test_literal_anycast_has_no_fabricated_country_but_has_attributed_asn():
    index = PrefixIntelligence.from_document(snapshot(), now=1_800_000_100)
    info = describe_proxy_endpoint(
        f"vless://{UUID}@1.1.1.1:443#France",
        intelligence=index,
    )
    assert info is not None
    assert info["ip"] == "1.1.1.1"
    assert info["host_kind"] == "public_ip_literal"
    assert info["asn"] == 13335
    assert info["as_org"] == "Example AS"
    assert info["cdn_provider"] == "Example CDN"
    assert info["anycast"] is True
    assert info["geo"]["country_code"] is None
    assert info["geo"]["status"] == "anycast_location_unknown"
    assert info["intelligence"]["provider"] == "offline-fixture"
    assert info["intelligence"]["prefix"] == "1.1.1.0/24"


def test_longest_prefix_wins_and_geo_carries_provider_provenance():
    index = PrefixIntelligence.from_document(snapshot(), now=1_800_000_100)
    info = describe_proxy_endpoint(
        "trojan://p@1.1.1.200:443#IR", intelligence=index
    )
    assert info is not None
    assert info["asn"] == 65001
    assert info["geo"]["country_code"] == "DE"
    assert info["geo"]["status"] == "prefix_dataset_estimate"
    assert info["cdn_provider"] is None
    assert info["anycast"] is False
    assert info["intelligence"]["prefix"] == "1.1.1.128/25"


def test_absent_prefix_and_private_addresses_remain_unknown():
    index = PrefixIntelligence.from_document(snapshot(), now=1_800_000_100)
    unknown = describe_proxy_endpoint(f"vless://{UUID}@8.8.8.8:443", intelligence=index)
    assert unknown is not None
    assert unknown["asn"] is None and unknown["geo"]["country_code"] is None
    private = describe_proxy_endpoint(f"vless://{UUID}@127.0.0.1:443", intelligence=index)
    assert private is not None
    assert private["host_kind"] == "non_public_ip_literal"
    assert private["ip"] is None
    assert private["asn"] is None
    assert private["geo"]["country_code"] is None


def test_vmess_and_ipv6_endpoint_extraction():
    vmess = {
        "v": "2", "ps": "US", "add": "1.1.1.1", "port": "443",
        "id": UUID, "net": "ws", "tls": "tls",
    }
    encoded = base64.b64encode(json.dumps(vmess).encode()).decode()
    identity = describe_proxy_endpoint("vmess://" + encoded)
    assert identity is not None
    assert identity["protocol"] == "vmess"
    assert identity["host"] == "1.1.1.1"
    assert identity["geo"]["country_code"] is None
    ipv6 = describe_proxy_endpoint(f"vless://{UUID}@[2606:4700:4700::1111]:8443")
    assert ipv6 is not None
    assert ipv6["ip_version"] == 6
    assert ipv6["host_kind"] == "public_ip_literal"


def test_udp_only_protocol_is_not_labeled_as_tcp_compatible():
    identity = describe_proxy_endpoint(
        "hysteria2://secret@1.1.1.1:443?insecure=0"
    )
    assert identity is not None
    assert identity["transport_kind"] == "udp"
    assert identity["protocol"] == "hysteria2"


@pytest.mark.parametrize(
    "payload",
    [
        snapshot(expires_at=1_799_999_999),
        snapshot(observed_at=1_800_000_101),
        snapshot(prefixes=[{"cidr": "10.0.0.0/8", "asn": 13335}]),
        snapshot(prefixes=[{"cidr": "1.1.1.1/24", "asn": 13335}]),
        snapshot(prefixes=[{"cidr": "1.1.1.0/24", "country_code": "USA"}]),
        snapshot(prefixes=[{"cidr": "1.1.1.0/24", "asn": True}]),
        snapshot(provider=""),
    ],
)
def test_prefix_index_rejects_invalid_untrusted_observations(payload):
    with pytest.raises(ValueError):
        PrefixIntelligence.from_document(payload, now=1_800_000_100)


def test_ineligible_link_does_not_leak_credentials_or_make_up_metadata():
    assert describe_proxy_endpoint("garbage-password-secret") is None
    assert describe_proxy_endpoint("vmess://this-is-not-valid-base64") is None
    url = "vless://password-secret@bad host:443#US"
    value = describe_proxy_endpoint(url)
    assert value is None or "password-secret" not in json.dumps(value)


def test_network_dataset_can_be_loaded_without_external_requests(tmp_path):
    p = tmp_path / "prefixes.json"
    p.write_text(json.dumps(snapshot()), encoding="utf-8")
    index = PrefixIntelligence.from_file(p, now=1_800_000_100)
    info = describe_proxy_endpoint(
        f"vless://{UUID}@1.1.1.1:443", intelligence=index
    )
    assert info is not None and info["asn"] == 13335
    assert re.fullmatch(r"[0-9a-f]{24}", info["endpoint_id"])
