"""The published dashboard must represent the admitted current feed."""
import json

import pytest

from scripts import generate_site_data as site


def test_current_dashboard_does_not_mix_historical_nodes(tmp_path, monkeypatch):
    first = "trojan://alpha@5.5.5.5:443?security=tls#Live"
    second = "trojan://beta@5.5.5.6:443?security=tls#Other"
    historical = "trojan://gamma@5.5.5.7:443?security=tls#Historical"
    (tmp_path / "all_sources.json").write_text(
        json.dumps({"entries": [
            {"protocol": "trojan", "address": "5.5.5.5", "port": 443,
             "tag": "Live", "raw": first},
            {"protocol": "trojan", "address": "5.5.5.6", "port": 443,
             "tag": "Other", "raw": second},
        ]}), encoding="utf-8"
    )
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "proxies.json").write_text(
        json.dumps({"proxies": [{"uri": historical}]}), encoding="utf-8"
    )
    monkeypatch.setattr(site, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", dev)
    current = site.parse_production_proxies()
    assert len(current) == 2
    assert {node["raw_uri"] for node in current} == {first, second}


def test_release_reconciliation_detects_missing_and_duplicate_nodes(
    tmp_path, monkeypatch
):
    first = "trojan://alpha@5.5.5.5:443?security=tls#Live"
    second = "trojan://beta@5.5.5.6:443?security=tls#Other"
    (tmp_path / "all_sources.txt").write_text(first + "\n" + second + "\n", encoding="utf-8")
    monkeypatch.setattr(site, "OUTPUTS_DIR", tmp_path)
    published = [{"raw_uri": first}, {"raw_uri": second}]
    assert site.assert_current_feed_parity(published)["admitted"] == 2
    with pytest.raises(ValueError, match="dashboard output loses"):
        site.assert_current_feed_parity([{"raw_uri": first}])
    with pytest.raises(ValueError, match="dashboard output loses"):
        site.assert_current_feed_parity(published + [{"raw_uri": first}])
