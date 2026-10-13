"""End-to-end regression tests for semantic proxy identity and honest labels."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from huntx.formats.npvt import (
    NpvtHandler, canonical_proxy_identity, format_evidence_remark,
)


ID = "11111111-2222-4333-8444-555555555555"
BASE = f"vless://{ID}@edge.example.com:443"


def remark(uri: str) -> str:
    return unquote(urlsplit(uri).fragment)


def test_equivalent_query_order_and_fragment_dedup_in_ingestion_and_build(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    first = BASE + "?type=ws&security=tls&path=%2Fws#ChannelOne"
    other = BASE + "?path=%2Fws&security=tls&type=ws#AnotherChannel"
    assert canonical_proxy_identity(first) == canonical_proxy_identity(other)
    records = NpvtHandler().parse(f"{first}\n{other}".encode(), {})
    assert len(records) == 1
    assert len(NpvtHandler().build(records).decode().splitlines()) == 1
    # Data arriving from separate raw observations must also dedup at export.
    merged = [{"data": {"line": first}}, {"data": {"line": other}}]
    assert len(NpvtHandler().build(merged).decode().splitlines()) == 1


def test_different_credential_transport_path_and_tls_remain_independent(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    first = BASE + "?type=ws&security=tls&path=%2Fone"
    different_password = first.replace(ID, "99999999-2222-4333-8444-555555555555")
    different_path = first.replace("%2Fone", "%2Ftwo")
    different_security = first.replace("security=tls", "security=reality&pbk=key")
    lines = [first, different_password, different_path, different_security]
    keys = [canonical_proxy_identity(link) for link in lines]
    assert len(set(keys)) == 4
    built = NpvtHandler().build([{"data": {"line": link}} for link in lines]).decode().splitlines()
    assert len(built) == 4
    tags = [remark(link) for link in built]
    assert len(set(tags)) == len(tags)  # No client-visible duplicate labels.


def test_hy2_alias_and_shadowsocks_encoding_use_one_semantic_identity():
    left = "hy2://pass@hy.example.org:443?sni=cdn.example.org#A"
    right = "hysteria2://pass@hy.example.org:443?sni=cdn.example.org#B"
    assert canonical_proxy_identity(left) == canonical_proxy_identity(right)
    userinfo = base64.urlsafe_b64encode(b"aes-256-gcm:secret").decode().rstrip("=")
    legacy = base64.urlsafe_b64encode(
        b"aes-256-gcm:secret@ss.example.org:8388"
    ).decode().rstrip("=")
    first = f"ss://{userinfo}@ss.example.org:8388#A"
    other = f"ss://{legacy}#B"
    assert canonical_proxy_identity(first) == canonical_proxy_identity(other)


def test_names_show_useful_safe_endpoint_details_instead_of_zz_hash():
    uri = BASE + "?security=tls&type=ws#anything"
    label = format_evidence_remark(uri)
    assert label.startswith("VLESS-WS-TLS | edge.example.com:443")
    assert "ZZ" not in label and "UNVERIFIED" not in label.upper()
    assert ID not in label
    assert len(label) <= 110
    assert format_evidence_remark(uri) == label


def test_dns_latency_and_speed_are_visible_only_when_measured_fresh_and_proven(monkeypatch):
    from huntx.formats import npvt
    monkeypatch.setattr(npvt.time, "time", lambda: 1_800_000_100)
    uri = BASE + "?type=ws&security=tls"
    fields = {
        "dns_status": "resolved", "dns_checked_at": 1_800_000_000,
        "dns_expires_at": 1_800_000_300,
        "latency_ms": 42, "probe_kind": "tcp_connect",
        "probe_checked_at": 1_800_000_000, "probe_expires_at": 1_800_000_300,
        "down_mbps": 54.2, "up_mbps": 17.8,  # configured limits, not measurements
    }
    tag = format_evidence_remark(uri, fields)
    assert "DNS:OK" in tag and "TCP:42ms" in tag
    assert "DL:" not in tag and "UL:" not in tag and "AUTH:" not in tag

    authenticated = {
        **fields, "speed_kind": "authenticated_throughput",
        "speed_authenticated": True, "download_mbps": 54.2, "upload_mbps": 17.8,
        "speed_checked_at": 1_800_000_000, "speed_expires_at": 1_800_000_300,
    }
    tag = format_evidence_remark(uri, authenticated)
    assert "DL:54.2Mb/s" in tag
    assert "UL:17.8Mb/s" in tag
    expired = {**authenticated, "speed_expires_at": 1_800_000_001,
               "dns_expires_at": 1_800_000_001, "probe_expires_at": 1_800_000_001}
    stale = format_evidence_remark(uri, expired)
    assert "DL:" not in stale and "UL:" not in stale
    assert "TCP:" not in stale and "DNS:" not in stale


def test_vmesses_with_different_user_visible_names_are_one_proxy(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    shared = {
        "v": "2", "add": "vm.example.org", "port": "443", "id": ID,
        "net": "ws", "tls": "tls",
    }

    def make(tag: str) -> str:
        return "vmess://" + base64.b64encode(
            json.dumps({**shared, "ps": tag}).encode()
        ).decode()
    assert canonical_proxy_identity(make("A")) == canonical_proxy_identity(make("B"))
    items = NpvtHandler().parse((make("A") + "\n" + make("B")).encode(), {})
    assert len(items) == 1
    raw = NpvtHandler().build(items).decode()
    decoded = json.loads(base64.b64decode(raw[8:] + "=" * (-len(raw[8:]) % 4)))
    assert "vm.example.org:443" in decoded["ps"]
    assert ID not in decoded["ps"]


def test_cumulative_merger_keeps_earliest_timestamp_and_distinct_profiles():
    script = Path(__file__).resolve().parents[1] / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_semantic", script)
    assert spec is not None and spec.loader is not None
    import sys
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    a = BASE + "?type=ws&security=tls"
    b = BASE + "?security=tls&type=ws"
    other = BASE.replace(ID, "44444444-2222-4333-8444-555555555555") + "?type=ws&security=tls"
    merged = module.merge_dev_manifests({a: 300}, {b: 120, other: 500})
    assert len(merged) == 2
    assert min(merged.values()) == 120
    assert 500 in merged.values()
    assert {canonical_proxy_identity(v) for v in merged} == {
        canonical_proxy_identity(a), canonical_proxy_identity(other)
    }


def test_static_dashboard_collapses_same_released_connection_in_multiple_inputs(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_site_data.py"
    spec = importlib.util.spec_from_file_location("generate_site_data_semantic", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    raw = BASE + "?type=ws&security=tls#first"
    alias = BASE + "?security=tls&type=ws#same"
    different = BASE.replace(ID, "44444444-2222-4333-8444-555555555555") + "?type=ws&security=tls#another"

    def entry(uri: str, tag: str) -> dict:
        return {
            "protocol": "vless", "address": "edge.example.com", "port": 443,
            "tag": tag, "params": {"type": "ws", "security": "tls"},
            "raw": uri, "user": ID,
        }
    (outputs / "all_sources.json").write_text(json.dumps({
        "entries": [entry(raw, "first"), entry(alias, "same"), entry(different, "another")],
    }), encoding="utf-8")
    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(module, "OUTPUTS_DEV_DIR", tmp_path / "outputs_dev")
    proxies = module.parse_production_proxies()
    assert len(proxies) == 2
    assert [item["name"] for item in proxies] == ["first", "another"]
