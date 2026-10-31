"""The periodic dev check must stage old fixtures without altering production feeds."""
from __future__ import annotations

from pathlib import Path
import json

from scripts.stage_dev_refresh_fixture import stage_legacy_release_fixture


UUID = "11111111-2222-4333-8444-555555555555"


def test_stage_legacy_release_deduplicates_only_identical_proxy_connections(tmp_path: Path):
    source = tmp_path / "historical"
    source.mkdir()
    a = f"vless://{UUID}@edge.example.com:443?security=tls&type=ws&path=%2Fws#original"
    b = f"vless://{UUID}@edge.example.com:443?path=%2Fws&type=ws&security=tls#alias"
    c = f"vless://{UUID}@other.example.com:443?security=tls&type=ws&path=%2Fws#independent"
    original = "\n".join([a, b, c]) + "\n"
    (source / "all_sources.txt").write_text(original, encoding="utf-8")
    (source / "related.json").write_text('{"untouched":true}', encoding="utf-8")

    staged = tmp_path / "stage"
    report = stage_legacy_release_fixture(source, staged)

    assert report == {"input": 3, "retained": 2, "duplicate_identities": 1}
    assert (staged / "all_sources.txt").read_text(encoding="utf-8") == a + "\n" + c + "\n"
    assert (source / "all_sources.txt").read_text(encoding="utf-8") == original
    assert (staged / "related.json").read_bytes() == (source / "related.json").read_bytes()


def test_staged_fixture_retains_different_credentials_and_tls_settings(tmp_path: Path):
    source = tmp_path / "historical"
    source.mkdir()
    first = f"vless://{UUID}@edge.example.com:443?security=tls"
    another = "vless://22222222-2222-4333-8444-555555555555@edge.example.com:443?security=tls"
    plaintext = f"vless://{UUID}@edge.example.com:443?security=none"
    (source / "all_sources.txt").write_text(
        "\n".join([first, another, plaintext]) + "\n", encoding="utf-8"
    )
    staged = tmp_path / "stage"
    report = stage_legacy_release_fixture(source, staged)
    assert report["duplicate_identities"] == 0
    assert (staged / "all_sources.txt").read_text(encoding="utf-8").splitlines() == [
        first, another, plaintext,
    ]


def test_stage_dev_refresh_rejects_empty_or_nonexistent_release_feed(tmp_path: Path):
    from pytest import raises

    source = tmp_path / "historical"
    source.mkdir()
    with raises(ValueError, match="missing|empty"):
        stage_legacy_release_fixture(source, tmp_path / "stage")

def test_legacy_staged_feed_passes_strict_parity_without_mutating_archive(tmp_path, monkeypatch):
    """End-to-end scratch generation exercises the real strict parity gate."""
    from scripts import generate_site_data as site

    source = tmp_path / "archived"
    source.mkdir()
    a = f"vless://{UUID}@edge.example.com:443?security=tls&type=ws&path=%2Fws#a"
    b = f"vless://{UUID}@edge.example.com:443?type=ws&path=%2Fws&security=tls#b"
    (source / "all_sources.txt").write_text(a + "\n" + b + "\n", encoding="utf-8")
    items = []
    for tag, raw in [("a", a), ("b", b)]:
        items.append({
            "protocol": "vless", "address": "edge.example.com",
            "port": 443, "tag": tag,
            "params": {"security": "tls", "type": "ws", "path": "/ws"},
            "raw": raw, "user": UUID,
        })
    (source / "all_sources.json").write_text(
        json.dumps({"total": 2, "entries": items}), encoding="utf-8"
    )
    staged = tmp_path / "staged-input"
    report = stage_legacy_release_fixture(source, staged)
    assert report["duplicate_identities"] == 1
    docs = tmp_path / "scratch-docs"
    monkeypatch.setattr(site, "OUTPUTS_DIR", staged)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", tmp_path / "no-dev")
    monkeypatch.setattr(site, "DOCS_DIR", docs)
    monkeypatch.setattr(site, "ARTIFACTS_DIR", docs / "artifacts")
    monkeypatch.setattr(site, "CATALOG_FILE", docs / "catalog.json")
    monkeypatch.setattr(site, "DATA_JS_FILE", docs / "assets/js/data.js")
    monkeypatch.setattr(site, "annotate_dns_resolution", lambda nodes: nodes)
    monkeypatch.setattr(site, "enrich_proxies_with_geoip", lambda nodes: nodes)
    monkeypatch.setattr(
        site, "probe_tcp_latency",
        lambda nodes: [dict(node, probe_ok=False, latency=None) for node in nodes],
    )
    site.generate_all()
    assert (docs / "assets/js/data.js").is_file()
    assert (source / "all_sources.txt").read_text(encoding="utf-8").splitlines() == [a, b]

