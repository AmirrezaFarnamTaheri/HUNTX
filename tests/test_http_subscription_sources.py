"""Offline contract tests for independently monitored public HTTPS sources."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import yaml

from huntx.config.schema import SourceConfig
from huntx.connectors.http_subscription.connector import (
    HttpSubscriptionConnector,
    validate_public_feed_url,
)
from huntx.connectors.http_subscription.parser import (
    MAX_FEED_BYTES,
    _mihomo_uri,
    normalize_feed,
)
from huntx.formats.proxy_uri_validator import validate_proxy_uri

UUID = "f58a62e3-27a0-4297-906c-2d01b12eff32"
URI = f"vless://{UUID}@1.1.1.1:443?security=tls&sni=example.com#sample"


def test_plaintext_and_base64_feeds_share_verified_node_identities():
    text = f"# generated\n{URI}\n{URI}\nnot-a-proxy\n"
    plain, report = normalize_feed(text.encode())
    encoded, b64_report = normalize_feed(base64.b64encode(text.encode()))
    assert plain == encoded
    assert plain.decode().count("vless://") == 1
    assert report["nodes"] == b64_report["nodes"] == 1
    assert b64_report["kind"] == "base64_links"
    assert validate_proxy_uri(plain.decode().strip())


def test_profile_bundle_is_audited_without_losing_fragment_semantics():
    profile = [{
        "inbounds": [{"protocol": "socks"}],
        "routing": {"rules": [{"outboundTag": "proxy"}]},
        "outbounds": [{
            "protocol": "vless", "tag": "proxy",
            "streamSettings": {"sockopt": {"dialerProxy": "fragment"}},
        }, {"protocol": "freedom", "tag": "fragment"}],
    }]
    payload, report = normalize_feed(json.dumps(profile).encode(), "xray_profile_audit")
    assert payload == b""
    assert report["kind"] == "xray_profile_audit"
    assert report["profiles"] == report["policy_bound_endpoints"] == 1
    with pytest.raises(ValueError, match="full JSON profiles"):
        normalize_feed(json.dumps(profile).encode())


def test_mihomo_yaml_converts_valid_links_but_skips_policy_bound_nodes():
    original = {
        "proxies": [
            {"name": "safe", "type": "vless", "server": "1.1.1.1", "port": 443,
             "uuid": UUID, "tls": True, "servername": "example.com"},
            {"name": "requires-hop", "type": "vless", "server": "1.1.1.1",
             "port": 443, "uuid": UUID, "dialer-proxy": "egress"},
            {"name": "unsupported-plugin", "type": "ss", "server": "1.1.1.1",
             "port": 443, "cipher": "aes-128-gcm", "password": "secret",
             "network": "ws"},
        ],
    }
    payload, report = normalize_feed(yaml.safe_dump(original).encode())
    assert report["kind"] == "mihomo"
    assert report["nodes"] == 1
    assert report["skipped_incompatible"] == 2
    assert payload.decode().startswith("vless://")


def test_mihomo_reality_converts_only_when_required_parameters_present():
    node = {
        "type": "vless", "name": "reality", "server": "1.1.1.1", "port": 443,
        "uuid": UUID, "tls": True, "servername": "www.example.com",
        "reality-opts": {"public-key": "abcd", "short-id": "a1b2"},
    }
    converted = _mihomo_uri(node)
    assert converted is not None and validate_proxy_uri(converted)
    assert "security=reality" in converted
    assert "pbk=abcd" in converted
    del node["reality-opts"]["public-key"]
    assert _mihomo_uri(node) is None


@pytest.mark.parametrize("payload", [
    b"", b"<html>Cloudflare error</html>", b"no nodes here",
    b"not*base64!", b'{"broken":true}', b"[" * 12,
    b"x" * (MAX_FEED_BYTES + 1),
])
def test_malformed_feeds_are_rejected_without_replacing_last_good(payload):
    with pytest.raises(ValueError):
        normalize_feed(payload)


@pytest.mark.parametrize("url", [
    "http://raw.githubusercontent.com/a/b",
    "https://localhost/sub",
    "https://127.0.0.1/sub",
    "https://169.254.169.254/latest/meta-data",
    "https://user:password@raw.githubusercontent.com/a/b",
    "https://raw.githubusercontent.com:8443/a",
    "https://raw.githubusercontent.com/a/b#fragment",
    "https://example.net/metadata",
])
def test_unapproved_urls_are_never_fetched(url):
    with pytest.raises(ValueError):
        validate_public_feed_url(url)


def test_connector_isolates_sources_and_uses_content_addressed_observations(monkeypatch):
    feed = HttpSubscriptionConnector(
        "https://raw.githubusercontent.com/example/repo/main/list.txt"
    )
    monkeypatch.setattr(feed, "_fetch", lambda: URI.encode())
    items = list(feed.list_new({}))
    assert len(items) == 2
    assert {item.metadata["filename"] for item in items} == {
        "public-subscription.txt", "public-subscription.npvtsub",
    }
    assert all(item.metadata["refresh_unchanged"] for item in items)
    assert all(item.metadata["parsed_nodes"] == 1 for item in items)
    assert feed.get_state()["report"]["nodes"] == 1
    assert all(item.data == items[0].data for item in items)


def test_connector_refuses_bad_upstream_without_emitting_empty_artifacts(monkeypatch):
    feed = HttpSubscriptionConnector(
        "https://raw.githubusercontent.com/example/repo/main/list.txt"
    )
    monkeypatch.setattr(feed, "_fetch", lambda: b"not valid content")
    with pytest.raises(ValueError):
        list(feed.list_new(None))
    assert feed.get_state() == {}


def test_registry_matches_production_sources_and_tracks_all_user_urls():
    root = Path(__file__).resolve().parents[1]
    registry = json.loads(
        (root / "configs/http_subscription_registry.json").read_text(encoding="utf-8")
    )
    config = yaml.safe_load((root / "configs/config.prod.yaml").read_text(encoding="utf-8"))
    sources = {
        source["id"]: source for source in config["sources"]
        if source["type"] == "http_subscription"
    }
    assert len(registry["sources"]) == registry["total"] == len(sources) == 34
    assert sum(not value["enabled"] for value in registry["sources"]) == 6
    for entry in registry["sources"]:
        source = sources[entry["id"]]
        settings = source["http_subscription"]
        assert settings["url"] == entry["url"]
        assert settings["mode"] == entry["mode"]
        assert settings.get("enabled", True) == entry["enabled"]
        assert source["required"] is False
        validated = SourceConfig.model_validate(source)
        assert validated.publication_eligible == entry["enabled"]
        assert source["id"] in config["publishing"]["routes"][0]["from_sources"]
    assert len(set(config["publishing"]["routes"][0]["from_sources"])) == len(
        config["publishing"]["routes"][0]["from_sources"]
    )


def test_required_telegram_sources_remain_unchanged_and_enabled():
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "configs/config.prod.yaml").read_text()
    )
    for src in config["sources"]:
        if src["type"] != "http_subscription":
            assert src.get("required", True) is True
            assert src["telegram_user"]["peer"]
    assert len(config["sources"]) >= 81 + 34


def test_go_fetcher_conditionally_reuses_only_verified_content(monkeypatch):
    import hashlib
    import subprocess

    class Store:
        def __init__(self):
            self.raw = {}

        def get(self, digest):
            return self.raw.get(digest)

    store = Store()
    endpoint = "https://raw.githubusercontent.com/example/repo/main/list.txt"
    requests = []

    def fake_run(command, **kwargs):
        requests.append(command)
        if len(requests) == 1:
            result = {
                "status": "ok", "etag": '"version-1"',
                "last_modified": "Mon, 12 Oct 2026 10:00:00 GMT",
                "content_b64": base64.b64encode(URI.encode()).decode(),
                "bytes": len(URI.encode()),
            }
        else:
            result = {"status": "not_modified"}
        return subprocess.CompletedProcess(command, 0, json.dumps(result).encode(), b"")

    monkeypatch.setattr(
        "huntx.connectors.http_subscription.connector._engine_path",
        lambda: "/tmp/huntx-engine",
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    feed = HttpSubscriptionConnector(endpoint, raw_store=store)
    first = list(feed.list_new())
    initial_state = feed.get_state()
    assert len(first) == 2
    digest = hashlib.sha256(first[0].data).hexdigest()
    assert initial_state["normalized_sha256"] == digest
    store.raw[digest] = first[0].data

    refreshed = HttpSubscriptionConnector(endpoint, raw_store=store)
    second = list(refreshed.list_new(initial_state))
    state = refreshed.get_state()
    assert second[0].data == first[0].data
    assert state["revalidated"] is True
    assert state["feed_sha256"] == initial_state["feed_sha256"]
    assert state["last_changed_at"] == initial_state["last_changed_at"]
    assert "--etag" not in requests[0] and "--etag" in requests[1]
    assert '"version-1"' in requests[1]


def test_go_fetcher_never_revalidates_missing_or_corrupt_cache(monkeypatch):
    import subprocess

    class Store:
        def get(self, digest):
            return b"wrong-content"

    observed = []

    def fake_run(command, **kwargs):
        observed.extend(command)
        response = {
            "status": "ok",
            "content_b64": base64.b64encode(URI.encode()).decode(),
            "bytes": len(URI.encode()),
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(response).encode(), b"")

    monkeypatch.setattr(
        "huntx.connectors.http_subscription.connector._engine_path",
        lambda: "/tmp/huntx-engine",
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    feed = HttpSubscriptionConnector(
        "https://raw.githubusercontent.com/example/repo/main/list.txt",
        raw_store=Store(),
    )
    list(feed.list_new({
        "normalized_sha256": "f" * 64,
        "etag": '"bad"',
    }))
    assert "--etag" not in observed
    assert feed.get_state()["revalidated"] is False


def test_reordered_feed_does_not_change_node_remark_identity(monkeypatch):
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "stable")
    from huntx.formats.npvt import NpvtHandler

    second = URI.replace(UUID, "de6d0001-4fe3-4ff8-aa13-593b49f65563")
    handler = NpvtHandler()
    records = handler.parse((URI + "\n" + second).encode(), {})
    assert len(records) == 2

    def tags(output):
        result = {}
        for line in output.decode().splitlines():
            part, _, tag = line.partition("#")
            result[part] = tag
        return result

    original = tags(handler.build(records))
    reordered = tags(handler.build(list(reversed(records))))
    assert original == reordered
    assert len(set(original.values())) == 2
    assert all(len(tag.rsplit("-", 1)[-1]) == 12 for tag in original.values())


@pytest.mark.parametrize("state", [
    {"probe_ok": False, "latency_ms": 18.0, "historical_success_rate": 1.0},
    {"is_active": False, "latency_ms": 18.0, "historical_success_rate": 1.0},
    {"status": "retired", "latency_ms": 18.0, "historical_success_rate": 1.0},
    {"lifecycle": "quarantined", "latency_ms": 18.0, "historical_success_rate": 1.0},
])
def test_rejected_or_dead_history_is_never_promoted_by_scoring(state):
    from huntx.core.scoring import ProxyScoringEngine

    assert ProxyScoringEngine().score_proxy(state) == 0.0
