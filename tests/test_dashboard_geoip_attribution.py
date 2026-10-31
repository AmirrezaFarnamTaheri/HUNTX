"""Publishing must retain evidence-backed regions and network owners."""

from __future__ import annotations

import pytest

from scripts import generate_site_data as site
from huntx.core.remark_geoip import (
    _load_asn_ranges,
    _load_ranges,
    estimate_as_organization,
    estimate_country,
)


@pytest.fixture
def attribution_tables(tmp_path, monkeypatch):
    """Small, deterministic replacements for the public PDDL IP databases."""
    country_v4 = tmp_path / "country-v4.csv"
    country_v4.write_text(
        "5.5.5.0,5.5.5.255,DE\n"
        "8.8.8.0,8.8.8.255,US\n",
        encoding="utf-8",
    )
    asn_v4 = tmp_path / "asn-v4.csv"
    asn_v4.write_text(
        '5.5.5.0,5.5.5.255,64501,"Example Network GmbH"\n'
        '8.8.8.0,8.8.8.255,15169,"Google LLC"\n',
        encoding="utf-8",
    )
    country_v6 = tmp_path / "country-v6.csv"
    country_v6.write_text("2a00:1450::,2a00:1450:ffff:ffff:ffff:ffff:ffff:ffff,NL\n", encoding="utf-8")
    asn_v6 = tmp_path / "asn-v6.csv"
    asn_v6.write_text('2a00:1450::,2a00:1450:ffff:ffff:ffff:ffff:ffff:ffff,15169,"Google LLC"\n', encoding="utf-8")

    monkeypatch.setenv("HUNTX_GEOIP_IPV4_CSV", str(country_v4))
    monkeypatch.setenv("HUNTX_GEOIP_IPV6_CSV", str(country_v6))
    monkeypatch.setenv("HUNTX_ASN_IPV4_CSV", str(asn_v4))
    monkeypatch.setenv("HUNTX_ASN_IPV6_CSV", str(asn_v6))
    monkeypatch.delenv("HUNTX_GEOIP_DISABLE", raising=False)
    _load_ranges.cache_clear()
    _load_asn_ranges.cache_clear()
    yield
    _load_ranges.cache_clear()
    _load_asn_ranges.cache_clear()


def test_offline_country_and_asn_lookup_use_public_ip_evidence(attribution_tables):
    assert estimate_country("5.5.5.23") == "DE"
    assert estimate_as_organization("5.5.5.23") == "Example Network GmbH"
    assert estimate_country("2a00:1450::1") == "NL"
    assert estimate_as_organization("2a00:1450::1") == "Google LLC"
    assert estimate_country("8.8.8.8") is None  # Anycast is not physical location
    assert estimate_country("10.0.0.1") is None
    assert estimate_as_organization("10.0.0.1") is None
    assert estimate_country("host.example.com") is None


def test_dashboard_geo_enrichment_uses_offline_evidence_and_overrides_weak_hints(attribution_tables, monkeypatch):
    def forbidden_online_lookup(_addresses):
        raise AssertionError("Offline datasets must not rely on an HTTP API")

    monkeypatch.setattr(site, "_geoip_batch_lookup", forbidden_online_lookup)
    monkeypatch.setattr(site, "_resolve_hostnames", lambda addresses: addresses)

    proxies = [
        {"server": "5.5.5.23", "country": "ZZ", "geo_source": "unknown", "geo_verified": False,
         "carrier": "Unverified", "org": "Unverified"},
        {"server": "5.5.5.24", "country": "IR", "geo_source": "unverified_country_hint", "geo_verified": False,
         "carrier": "Unverified", "org": "Unverified"},
        {"server": "8.8.8.8", "country": "ZZ", "geo_source": "anycast-provider", "geo_verified": False,
         "carrier": "Unverified", "org": "Unverified"},
        {"server": "10.0.0.1", "country": "ZZ", "geo_source": "unknown", "geo_verified": False,
         "carrier": "Unverified", "org": "Unverified"},
    ]
    enriched = site.enrich_proxies_with_geoip(proxies)
    for entry in enriched[:2]:
        assert entry["country"] == "DE"
        assert entry["country_name"] == "Germany"
        assert entry["flag"] == "🇩🇪"
        assert entry["carrier"] == "Example Network GmbH"
        assert entry["org"] == "Example Network GmbH"
        assert entry["geo_verified"] is True
        assert entry["geo_source"] == "server-country-pddl"
        assert entry["latitude"] is None
        assert entry["longitude"] is None

    assert enriched[2]["country"] == "ZZ"  # Anycast remains unattributed
    assert enriched[2]["geo_verified"] is False
    assert enriched[3]["country"] == "ZZ"  # Private addresses cannot be geolocated


def test_no_dataset_never_fabricates_country_or_network(attribution_tables, monkeypatch):
    monkeypatch.delenv("HUNTX_GEOIP_IPV4_CSV")
    monkeypatch.delenv("HUNTX_GEOIP_IPV6_CSV")
    monkeypatch.delenv("HUNTX_ASN_IPV4_CSV")
    monkeypatch.delenv("HUNTX_ASN_IPV6_CSV")
    assert estimate_country("5.5.5.23") is None
    assert estimate_as_organization("5.5.5.23") is None


def test_explicit_geoip_opt_out_does_not_enrich(attribution_tables, monkeypatch):
    monkeypatch.setenv("HUNTX_GEOIP_DISABLE", "1")
    node = {"server": "5.5.5.23", "country": "ZZ", "geo_source": "unknown", "geo_verified": False}
    assert site.enrich_proxies_with_geoip([node])[0]["country"] == "ZZ"


def test_endpoint_inventory_reuses_verified_offline_country_without_guessing_hostnames(attribution_tables):
    from huntx.core.endpoint_intelligence import describe_proxy_endpoint

    literal = describe_proxy_endpoint(
        "vless://11111111-2222-3333-4444-555555555555@5.5.5.23:443"
    )
    assert literal is not None
    assert literal["geo"] == {
        "status": "ip_allocation_country_estimate", "country_code": "DE"
    }
    assert literal["as_org"] == "Example Network GmbH"
    assert literal["asn"] is None  # An AS organization string is not an ASN measurement
    assert literal["intelligence"]["status"] == "offline_allocation_dataset"

    hostname = describe_proxy_endpoint(
        "vless://11111111-2222-3333-4444-555555555555@edge.example.com:443#DE"
    )
    assert hostname is not None
    assert hostname["geo"]["country_code"] is None
    assert hostname["as_org"] is None

    anycast = describe_proxy_endpoint(
        "vless://11111111-2222-3333-4444-555555555555@8.8.8.8:443#US"
    )
    assert anycast is not None
    assert anycast["geo"]["country_code"] is None
    assert anycast["anycast"] is True
