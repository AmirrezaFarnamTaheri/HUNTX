"""Rich client tags retain provenance, stable identity and feed parity."""

import base64
import json
from urllib.parse import unquote, urlsplit

from huntx.formats.npvt import NpvtHandler, add_clean_remark


UUID = "11111111-2222-3333-4444-555555555555"
URI = f"vless://{UUID}@1.1.1.1:443?type=ws&security=tls#Germany"


def evidence(country="DE", *, expires=4_000_000_000):
    return {
        "endpoint": {
            "schema_version": 1,
            "geo": {"status": "prefix_dataset_estimate", "country_code": country},
            "intelligence": {
                "status": "matched", "provider": "offline-fixture",
                "observed_at": 1_800_000_000, "expires_at": expires,
            },
            "asn": 13335, "as_org": "Example Networks",
            "cdn_provider": "Example CDN",
            "transport": "ws", "tls_mode": "tls",
        }
    }


def test_rich_remark_has_verified_country_flag_provenance_transport_asn_and_stable_id(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    tag = unquote(urlsplit(add_clean_remark(URI, {}, evidence())).fragment)
    assert tag.startswith("🇩🇪 VLESS-WS-TLS | 1.1.1.1:443")
    assert "🇩🇪 DE" not in tag
    assert "VLESS" in tag and "WS" in tag and "TLS" in tag
    assert "AS13335" in tag
    assert "CDN" in tag
    assert "✔" not in tag and "⭐" not in tag
    assert UUID not in tag and "Example Networks" not in tag
    assert len(tag) <= 110
    second = unquote(urlsplit(add_clean_remark(URI, {"vless": 300}, evidence())).fragment)
    assert tag == second


def test_absent_or_stale_evidence_does_not_make_up_country_asn_or_cdn(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    no_evidence = unquote(urlsplit(add_clean_remark(URI, {})).fragment)
    stale = unquote(urlsplit(add_clean_remark(URI, {}, evidence(expires=1))).fragment)
    for remark in (no_evidence, stale):
        assert remark.startswith("🌐 VLESS-WS-TLS | 1.1.1.1:443")
        assert "ZZ" not in remark
        assert "1.1.1.1:443" in remark
        assert "🇩🇪" not in remark and "AS13335" not in remark
        assert "CDN" not in remark
    assert "VLESS" in no_evidence


def test_unverified_source_country_hint_is_conspicuously_marked(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    metadata = {"country_hint": "FR", "country_hint_source": "source_remark"}
    remark = unquote(urlsplit(add_clean_remark(URI, {}, metadata)).fragment)
    assert remark.startswith("🇫🇷? VLESS-WS-TLS | 1.1.1.1:443")
    assert "🇫🇷? FR" not in remark
    assert "AS" not in remark
    assert "⭐" not in remark


def test_evidence_remark_round_trips_through_npvt_and_vmess(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    handler = NpvtHandler()
    records = [{"data": {"line": URI.split("#")[0], **evidence()}}]
    built = handler.build(records).decode()
    assert "%F0%9F" in built
    assert "🇩🇪" in unquote(urlsplit(built).fragment)
    assert handler.build(records) == handler.build(records)

    vmess = {
        "v": "2", "ps": "old", "add": "1.1.1.1", "port": "443",
        "id": UUID, "net": "ws", "tls": "tls",
    }
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    changed = add_clean_remark(link, {}, evidence())
    payload = changed[8:] + "=" * (-len(changed[8:]) % 4)
    assert "🇩🇪" in json.loads(base64.b64decode(payload))["ps"]


def test_legacy_format_remains_unchanged_when_opt_in_is_absent(monkeypatch):
    monkeypatch.delenv("HUNTX_REMARK_STYLE", raising=False)
    remark = add_clean_remark(URI, {})
    assert remark.endswith("#vless-ws-tls-1")


def test_unverified_marketing_hint_is_preserved_separately_from_canonical_uri(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    source = f"vless://{UUID}@1.1.1.1:443#FR%20Node"
    records = NpvtHandler().parse(source.encode(), {})
    assert len(records) == 1
    assert records[0]["data"]["line"] == source.split("#")[0]
    assert records[0]["data"]["country_hint"] == "FR"
    assert records[0]["data"]["country_hint_source"] == "source_remark"


def test_legacy_records_receive_fresh_offline_evidence_during_build(monkeypatch, tmp_path):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    intel = tmp_path / "current-prefixes.json"
    import time

    now = int(time.time())
    intel.write_text(json.dumps({
        "schema_version": 1, "provider": "offline-fixture",
        "observed_at": now - 120, "expires_at": now + 3600,
        "prefixes": [{"cidr": "1.1.1.0/24", "asn": 13335,
                      "country_code": "DE", "anycast": False}],
    }), encoding="utf-8")
    monkeypatch.setenv("HUNTX_NETWORK_INTELLIGENCE_PATH", str(intel))
    stored_legacy = [{"data": {"line": URI.split("#")[0]}}]
    tag = unquote(urlsplit(NpvtHandler().build(stored_legacy).decode()).fragment)
    assert tag.startswith("🇩🇪 VLESS-WS-TLS | 1.1.1.1:443")
    assert "🇩🇪 DE" not in tag
    assert "AS13335" in tag
    assert "VLESS-WS-TLS" in tag
    assert "⭐" not in tag
