"""The dashboard must name a node exactly as the imported feed does.

The published artifacts carry a clean protocol-index remark (``vless-1``)
produced by ``huntx.formats.npvt.add_clean_remark``. The dashboard used to
compose its own display name as ``{country}-{tag}``, so a node the site listed
as ``NL-vless-1`` arrived in a client as ``vless-1`` and neither name could be
used to find the other. Country, flag and carrier are separate published fields
that the UI already renders on their own, so the prefix was pure duplication.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_site_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_site_data", ROOT / "scripts" / "generate_site_data.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_release(outputs: Path, uri: str, tag: str) -> None:
    """Write the one release artifact the dashboard reads proxy records from."""
    outputs.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": 1,
        "protocols": {"vless": 1},
        "entries": [
            {
                "protocol": "vless",
                "address": "198.51.100.7",
                "port": 443,
                "tag": tag,
                "params": {"security": "reality", "type": "tcp"},
                "raw": uri,
                "user": "11111111-2222-3333-4444-555555555555",
            }
        ],
    }
    (outputs / "all_sources_npvt_decoded.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_dashboard_name_is_the_published_remark_without_a_country_prefix(tmp_path, monkeypatch):
    module = _load_site_generator()
    outputs = tmp_path / "outputs"
    outputs_dev = tmp_path / "outputs_dev"
    _write_release(outputs, "vless://u@198.51.100.7:443#vless-1", "vless-1")

    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(module, "OUTPUTS_DEV_DIR", outputs_dev)
    monkeypatch.setattr(module, "resolve_geo_and_carrier", lambda *a, **k: {
        "country": "NL", "country_name": "Netherlands", "flag": "🇳🇱",
        "carrier": "Serverius / NL", "org": "Serverius", "city": "Amsterdam",
        "latitude": 52.37, "longitude": 4.90,
        "geo_source": "tld", "geo_verified": False,
    })

    proxies = module.parse_production_proxies()

    assert len(proxies) == 1
    proxy = proxies[0]
    # The client shows "vless-1", so the site shows "vless-1".
    assert proxy["name"] == "vless-1"
    assert not proxy["name"].startswith("NL-")
    # Geography is still published, just not glued onto the remark.
    assert proxy["country"] == "NL"
    assert proxy["country_name"] == "Netherlands"
    assert proxy["flag"] == "🇳🇱"


def test_dashboard_name_survives_a_remark_that_is_not_a_protocol_index(tmp_path, monkeypatch):
    module = _load_site_generator()
    outputs = tmp_path / "outputs"
    outputs_dev = tmp_path / "outputs_dev"
    _write_release(outputs, "trojan://pw@198.51.100.9:443#My Relay", "My Relay")

    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(module, "OUTPUTS_DEV_DIR", outputs_dev)
    monkeypatch.setattr(module, "resolve_geo_and_carrier", lambda *a, **k: {
        "country": "DE", "country_name": "Germany", "flag": "🇩🇪",
        "carrier": "Hetzner", "org": "Hetzner", "city": "Frankfurt",
        "latitude": 50.11, "longitude": 8.68,
        "geo_source": "tld", "geo_verified": False,
    })

    proxies = module.parse_production_proxies()

    assert proxies[0]["name"] == "My Relay"
    assert proxies[0]["country"] == "DE"


def test_no_source_composes_a_country_prefixed_display_name():
    """Guard the composition itself, so it cannot creep back in silently."""
    source = (ROOT / "scripts" / "generate_site_data.py").read_text(encoding="utf-8")
    assert '"name": tag' in source
    assert "geo['country']}-{tag}" not in source
    assert 'geo["country"]}-{tag}' not in source
