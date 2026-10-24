"""Regression cases from the 2026-10-24 published-artifact audit.

These tests exercise the final artifacts and their evidence contracts rather
than accepting a green intermediate build as proof of a usable release.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

from huntx.formats.common.clash import build_clash_subscription_bytes
from huntx.formats.npvt import NpvtHandler
from scripts import assemble_generated_snapshot as assembler
from scripts import generate_site_data as site


UUID = "11111111-2222-3333-4444-555555555555"


def test_publication_snapshot_preserves_complete_application_shell(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint"
    (checkpoint / "outputs").mkdir(parents=True)
    (checkpoint / "outputs" / "all_sources.txt").write_text("node\n")
    (tmp_path / "dist").mkdir()
    (tmp_path / "logs").mkdir()
    dashboard = tmp_path / "data-only"
    (dashboard / "artifacts" / "release").mkdir(parents=True)
    (dashboard / "catalog.json").write_text(
        json.dumps({"files": [], "total_files": 0, "total_size": 0,
                    "total_size_str": "0 B"}), encoding="utf-8"
    )
    shell = tmp_path / "shell"
    for name, body in (
        ("index.html", '<script type="module" src="assets/js/app.js"></script>'),
        ("assets/js/app.js", "export const ready = true;\n"),
        ("assets/js/boot-guard.js", "window.bootGuard = true;\n"),
        ("assets/css/tailwind.css", "body { display: block; }\n"),
        ("manifest.json", '{"name":"HUNTX"}'),
        ("sw.js", "// service worker\n"),
        ("assets/js/data.js",
         'export const FALLBACK_CATALOG = {"files":[]};\n\n'
         'export const SAMPLE_PROXIES = [];\n'
         'export const INGEST_STATS = {"total_published_files":0,'
         '"total_storage_bytes":0,"total_storage_str":"0 B"};\n'),
        ("assets/js/bundle.js", "// obsolete bundle\n"),
    ):
        target = shell / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    target = tmp_path / "published"
    assembler.assemble_snapshot(
        checkpoint_root=checkpoint, dist_root=tmp_path / "dist",
        logs_root=tmp_path / "logs", destination=target,
        run_id="42", run_attempt="1", head_sha="abc", head_branch="main",
        source_created_at="2026-10-24T08:09:00Z",
        dashboard_root=dashboard, shell_root=shell,
    )
    for name in ("assets/js/app.js", "assets/js/boot-guard.js",
                 "assets/css/tailwind.css", "manifest.json", "sw.js"):
        assert (target / "docs" / name).is_file(), name
    assert not (target / "docs" / "assets/js/bundle.js").exists()


def test_clash_omits_invalid_sni_instead_of_shipping_unloadable_yaml() -> None:
    good = "hysteria2://pass@5.5.5.5:443?sni=good.example.com#Good"
    # UTF-8 percent-decoding yields a C1 control, invalid in YAML hostnames.
    bad = "hysteria2://pass@5.5.5.6:443?sni=%C2%9Fbroken.example.com#Bad"
    unicode_name = "hysteria2://pass@5.5.5.7:443?sni=good.example.com#%F0%9F%87%A9%F0%9F%87%AA%20Good"
    output = build_clash_subscription_bytes(good + "\n" + bad + "\n" + unicode_name)
    document = yaml.safe_load(output)
    assert [p["name"] for p in document["proxies"]] == ["Good", "🇩🇪 Good"]
    assert "\\ud83c" not in output.decode("utf-8")
    assert "🇩🇪" in output.decode("utf-8")
    assert "\u009f" not in output.decode("utf-8")


def test_vmess_nested_decoded_object_survives_dashboard_parsing(
    tmp_path: Path, monkeypatch
) -> None:
    vmess = {"v": "2", "ps": "Example", "add": "5.5.5.5",
             "port": "443", "id": UUID, "net": "ws", "tls": "tls"}
    raw = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    (tmp_path / "all_sources.json").write_text(
        json.dumps({"entries": [
            {"protocol": "vmess", "raw": raw, "decoded": vmess, "tag": "Example"}
        ]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(site, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", tmp_path / "missing-dev")
    result = site.parse_production_proxies()
    assert len(result) == 1
    assert result[0]["server"] == "5.5.5.5"
    assert result[0]["port"] == 443
    assert result[0]["security"] == "tls"
    assert result[0]["transport"] == "ws"


def test_implicit_tls_protocols_are_not_mislabeled_plaintext(
    tmp_path: Path, monkeypatch
) -> None:
    entries = [
        {"protocol": "trojan", "address": "5.5.5.5", "port": 443,
         "tag": "trojan", "raw": "trojan://secret@5.5.5.5:443"},
        {"protocol": "hysteria2", "address": "5.5.5.6", "port": 443,
         "tag": "hy2", "raw": "hysteria2://secret@5.5.5.6:443"},
    ]
    (tmp_path / "all_sources.json").write_text(
        json.dumps({"entries": entries}), encoding="utf-8"
    )
    monkeypatch.setattr(site, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", tmp_path / "missing-dev")
    result = site.parse_production_proxies()
    assert len(result) == 2
    assert [p["security"] for p in result] == ["tls", "tls"]


def test_authenticated_proxy_keeps_independent_dns_and_country_observations(
    monkeypatch,
) -> None:
    now = time.time()
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "evidence")
    monkeypatch.setenv("HUNTX_REMARK_TCP_PROBE", "1")
    monkeypatch.setattr(
        "huntx.core.remark_probe.probe_remark_evidence",
        lambda links: {links[0]: {
            "geoip_address": "5.5.5.5", "dns_status": "resolved",
            "dns_checked_at": now, "dns_expires_at": now + 900,
            "probe_kind": "tcp_connect", "latency_ms": 1,
            "probe_checked_at": now, "probe_expires_at": now + 900,
        }},
    )
    monkeypatch.setattr(
        "huntx.formats.npvt.estimate_country",
        lambda address: "DE" if address == "5.5.5.5" else None,
    )
    link = "trojan://secret@host.example.com:443?sni=good.example.com"
    result = NpvtHandler().build([{"data": {
        "line": link, "probe_kind": "protocol_authenticated",
        "probe_authenticated": True, "latency_ms": 55,
        "probe_checked_at": now, "probe_expires_at": now + 300,
    }}]).decode("utf-8")
    tag = unquote(urlsplit(result).fragment)
    assert tag.startswith("🇩🇪 TROJAN")
    assert "DNS:OK" in tag
    assert "AUTH:55ms" in tag
    assert "TCP:1ms" not in tag


def test_cumulative_count_is_reconciled_after_history_is_assembled(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    js = docs / "assets" / "js"
    js.mkdir(parents=True)
    (docs / "artifacts" / "dev").mkdir(parents=True)
    (docs / "catalog.json").write_text(
        json.dumps({"files": [], "total_files": 0,
                    "total_size": 0, "total_size_str": "0 B"}),
        encoding="utf-8",
    )
    (docs / "artifacts" / "dev" / "proxies.json").write_text(
        json.dumps({"_count": 42, "proxies": []}), encoding="utf-8",
    )
    (js / "data.js").write_text(
        'export const FALLBACK_CATALOG = {"files":[]};\n\n'
        'export const SAMPLE_PROXIES = [];\n\n'
        'export const INGEST_STATS = {"total_cumulative_nodes":0};\n',
        encoding="utf-8",
    )
    assembler.sync_dashboard_fallback_catalog(docs)
    assert '"total_cumulative_nodes":42' in (js / "data.js").read_text()
