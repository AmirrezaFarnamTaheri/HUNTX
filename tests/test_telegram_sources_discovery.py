"""Keep peer-sourced Telegram candidates separate from publication-approved sources."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_peer_source_candidates_are_deduplicated_and_not_production_ingested():
    data = json.loads((ROOT / "configs" / "telegram_source_candidates.json").read_text())
    assert data["schema"] == "huntx.telegram_source_candidates.v1"
    assert data["status"] == "unverified_research_only"
    assert data["ingestion_enabled"] is False
    assert len(data["channels"]) >= 500
    assert len(data["sources_examined"]) >= 8
    assert len(data["numeric_id_candidates"]) >= 25
    numeric = data["numeric_id_candidates"]
    assert len({item["peer"] for item in numeric}) == len(numeric)
    assert all(item["trust_state"] == "candidate" for item in numeric)
    assert all(item["source"].startswith("https://github.com/fifthidea/sub")
               for item in numeric)

    candidates = data["channels"]
    names = [item["username"].lower() for item in candidates]
    assert len(names) == len(set(names))
    assert all(item["trust_state"] == "candidate" for item in candidates)
    assert all(item["discovered_from"] for item in candidates)
    assert all(
        source.startswith("https://github.com/")
        for item in candidates for source in item["discovered_from"]
    )

    # A peer aggregator listing a handle is not proof of a working source.
    config = yaml.safe_load((ROOT / "configs" / "config.prod.yaml").read_text())
    production = {
        source["telegram_user"]["peer"].removeprefix("@").lower()
        for source in config["sources"]
        if source["type"] == "telegram_user" and source.get("telegram_user")
        and source["telegram_user"]["peer"].startswith("@")
    }
    assert not production.intersection(names)
    production_numeric = {
        source["telegram_user"]["peer"]
        for source in config["sources"]
        if source["type"] == "telegram_user" and source.get("telegram_user")
        and source["telegram_user"]["peer"].startswith("-100")
    }
    assert not production_numeric.intersection(item["peer"] for item in numeric)

    for handle in ("whitedns", "whitedns_group", "v2cnf", "ConfigWireguard", "V2ray_Alpha", "ProxyMTProto", "abc_vpn_configs", "OnlineVpnConfigs", "v2ray_free_conf", "ConfigOrg"):
        found = next(
            source for source in config["sources"]
            if source["type"] == "telegram_user" and source.get("telegram_user")
            and source["telegram_user"]["peer"].lower() == "@" + handle.lower()
        )
        assert found.get("trust_state", "approved") == "approved"
        assert found["discovered_from"] and found["approval_evidence"]
        assert any("https://t.me/" in value for value in found["approval_evidence"])
