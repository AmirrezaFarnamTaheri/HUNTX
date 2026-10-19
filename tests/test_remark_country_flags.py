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
    assert decoded["ps"].startswith("🇩🇪? VMESS")


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
