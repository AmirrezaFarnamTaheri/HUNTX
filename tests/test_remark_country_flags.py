"""Regression: real country metadata must not collapse to the unknown globe."""

import base64
import json
from urllib.parse import quote, unquote, urlsplit

import pytest

from huntx.formats.npvt import (
    NpvtHandler,
    _remark_country_hint,
    format_evidence_remark,
)


UUID = "11111111-2222-3333-4444-555555555555"


@pytest.mark.parametrize("fragment, country", [
    ("🇩🇪 Germany | WS", "DE"),
    ("🇳🇱 Amsterdam", "NL"),
    ("Germany", "DE"),
    ("France - fast server", "FR"),
    ("EG | Cairo", "EG"),
])
def test_source_location_hints_survive_remark_parsing(fragment, country):
    uri = f"vless://{UUID}@edge.example.net:443#" + quote(fragment)
    assert _remark_country_hint(uri) == country


def test_vmess_ps_field_is_checked_before_the_original_name_is_removed(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    payload = {
        "v": "2", "ps": "🇩🇪 Germany | WS", "add": "edge.example.net",
        "port": "443", "id": UUID, "net": "ws", "tls": "tls",
    }
    uri = "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode()
    records = NpvtHandler().parse(uri.encode(), {})
    assert len(records) == 1
    assert records[0]["data"]["country_hint"] == "DE"
    built = NpvtHandler().build(records).decode()
    decoded = json.loads(base64.b64decode(built[8:] + "=" * (-len(built[8:]) % 4)))
    assert decoded["ps"].startswith("🇩🇪 VMESS")


def test_offline_evidence_not_limited_to_a_short_handpicked_country_list(monkeypatch):
    monkeypatch.setattr("huntx.formats.npvt.time.time", lambda: 1800000100)
    uri = f"vless://{UUID}@198.18.1.4:443?security=tls"
    evidence = {
        "endpoint": {
            "geo": {"status": "prefix_dataset_estimate", "country_code": "EG"},
            "intelligence": {"status": "matched", "expires_at": 1800003600},
        },
    }
    assert format_evidence_remark(uri, evidence).startswith("🇪🇬 VLESS-TLS")


def test_offline_ip_country_works_and_anycast_stays_unknown(tmp_path, monkeypatch):
    from huntx.core.remark_geoip import estimate_country, _load_ranges
    dataset = tmp_path / "country.csv"
    dataset.write_text(
        "5.5.5.0,5.5.5.255,DE\n"
        "8.8.8.0,8.8.8.255,US\n"
        "2001:db8::,2001:db8::ffff,DE\n",
        encoding="utf-8",
    )
    _load_ranges.cache_clear()
    monkeypatch.setenv("HUNTX_GEOIP_IPV4_CSV", str(dataset))
    assert estimate_country("5.5.5.23") == "DE"
    assert estimate_country("8.8.8.8") is None
    assert estimate_country("10.0.0.1") is None
    assert estimate_country("edge.example.com") is None


def test_country_database_reaches_published_remark(tmp_path, monkeypatch):
    from huntx.core.remark_geoip import _load_ranges
    dataset = tmp_path / "country.csv"
    dataset.write_text("5.5.5.0,5.5.5.255,DE\n", encoding="utf-8")
    _load_ranges.cache_clear()
    monkeypatch.setenv("HUNTX_GEOIP_IPV4_CSV", str(dataset))
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    monkeypatch.delenv("HUNTX_REMARK_TCP_PROBE", raising=False)
    uri = f"vless://{UUID}@5.5.5.23:443?security=tls"
    lines = NpvtHandler().build([{"data": {"line": uri}}]).decode()
    assert unquote(urlsplit(lines).fragment).startswith("🇩🇪 VLESS-TLS")
