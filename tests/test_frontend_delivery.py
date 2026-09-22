"""Regression checks for the static dashboard delivery contract."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def _load_frontend_builder():
    spec = importlib.util.spec_from_file_location(
        "update_frontend", ROOT / "scripts" / "update_frontend.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_index_matches_frontend_generator() -> None:
    builder = _load_frontend_builder()
    expected = builder.build_index_content(ROOT)
    published = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert published == expected
    assert 'src="assets/js/bundle.js"' not in published
    assert 'type="module" src="assets/js/app.js"' in published
    assert 'cdn.tailwindcss.com' not in published
    assert 'assets/css/tailwind.css' in published
    assert not (ROOT / "docs" / "assets" / "js" / "bundle.js").exists()


def test_service_worker_uses_network_first_for_deployment_shell() -> None:
    worker = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")

    assert "const deploymentShell" in worker
    assert "(freshReleaseData || deploymentShell) ? networkFirst(event.request)" in worker
    assert "assets/js/app.js" in worker
    assert "assets/css/tailwind.css" in worker
    assert "assets/js/bundle.js" not in worker
    assert "Promise.allSettled" in worker
    assert "await caches.delete(CACHE_NAME)" in worker
    assert "throw new Error(`[HUNTX-SW] Cache prefetch failed" in worker
    assert "self.skipWaiting()" in worker
    assert "self.clients.claim()" in worker


def test_frontend_verifies_the_catalogued_proxy_artifact() -> None:
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")

    assert "crypto.subtle.digest(\"SHA-256\"" in application
    assert "loadVerifiedJsonArtifact" in application
    assert "getDecodedArtifactRecord" in application


def test_frontend_i18n_supports_requested_locales_and_rtl() -> None:
    i18n = (ROOT / "docs" / "assets" / "js" / "i18n.js").read_text(encoding="utf-8")
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    for locale in ('"fa"', '"zh-CN"', '"ru"'):
        assert locale in i18n
    assert 'document.documentElement.dir = locale === "fa" ? "rtl" : "ltr"' in i18n
    assert 'new URLSearchParams(globalThis.location?.search || "").get("lang")' in i18n
    assert 'id="language-selector"' in application
    assert "i18n.setLocale" in application
    # Runtime rendering now translates newly inserted subtrees only. Watching every
    # character/attribute mutation caused unnecessary full-document churn on rerenders.
    assert "characterData: true" not in i18n
    assert "attributeFilter:" not in i18n
    assert "childList: true" in i18n
    assert "subtree: true" in i18n
    for key in ("Telemetry Radar", "Live Proxies", "Protocol Studio", "Protocol Inspector", "Artifacts & Feeds", "Germany", "United States", "Iran"):
        assert f'"{key}"' in i18n
    assert 'id="toast-container" role="status" aria-live="polite" aria-atomic="true"' in html


def test_i18n_module_is_included_before_application_module() -> None:
    builder = _load_frontend_builder()

    html = builder.build_index_content(ROOT)
    assert 'type="module" src="assets/js/app.js"' in html
    assert 'import { i18n } from "./i18n.js";' in (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")


def test_cloudflare_anycast_geo_is_not_fabricated() -> None:
    """The static producer must not turn an anycast prefix into a fictional city."""
    import importlib.util

    module_path = ROOT / "scripts" / "generate_site_data.py"
    spec = importlib.util.spec_from_file_location("huntx_site_generator_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    geo = module.resolve_geo_and_carrier("104.21.12.34")
    assert geo["country"] == "ZZ"
    assert geo["carrier"] == "Cloudflare Anycast"
    assert geo["latitude"] is None
    assert geo["longitude"] is None
    assert geo["geo_source"] == "anycast-provider"


def test_production_packaging_requires_current_frontend_assets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "huntx.yml").read_text(encoding="utf-8")
    package = workflow.split("          try_package() {", 1)[1].split("          restore_previous_outputs()", 1)[0]
    required = []
    for line in package.splitlines():
        stripped = line.strip()
        for prefix in ('test -f "$candidate_dir/', 'test -s "$candidate_dir/'):
            if stripped.startswith(prefix):
                required.append(stripped[len(prefix):].split('"', 1)[0])
    assert {"index.html", "assets/js/app.js", "assets/css/tailwind.css", "sw.js"} <= set(required)
    assert "assets/js/bundle.js" not in required
    for relative in required:
        assert (ROOT / "docs" / relative).is_file(), relative


# ---------------------------------------------------------------------------
# B7 regression tests: GeoIP enrichment, TCP probes, catalog tags, feeds filter


def _load_site_generator():
    spec = importlib.util.spec_from_file_location(
        "huntx_site_generator", ROOT / "scripts" / "generate_site_data.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _proxy(**overrides):
    proxy = {
        "server": "203.0.113.10",
        "port": 443,
        "country": "ZZ",
        "geo_source": "unknown",
        "carrier": "Unverified",
        "org": "Unverified",
        "city": "Unknown",
        "latitude": None,
        "longitude": None,
        "geo_verified": False,
    }
    proxy.update(overrides)
    return proxy


def test_geoip_enrichment_falls_back_offline() -> None:
    """A GeoIP network failure must leave the offline heuristic record in place."""
    module = _load_site_generator()
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_GEOIP_DISABLE", None)
        # A raised network error yields an empty record set with identity translation.
        with mock.patch.object(module.urllib.request, "urlopen", side_effect=OSError("offline")):
            records, translation = module._geoip_batch_lookup(["203.0.113.10"])
        assert records == {}
        assert translation == {"203.0.113.10": "203.0.113.10"}
        # An empty record set must leave the offline heuristic untouched.
        with mock.patch.object(module, "_geoip_batch_lookup", return_value=({}, {})):
            proxies = module.enrich_proxies_with_geoip([_proxy()])
    assert proxies[0]["country"] == "ZZ"
    assert proxies[0]["geo_source"] == "unknown"
    assert proxies[0]["geo_verified"] is False
    assert proxies[0]["carrier"] == "Unverified"


def test_geoip_enrichment_sets_measured_geo_for_unknown_nodes() -> None:
    """Measured GeoIP fills explicitly-unknown geography; anycast prefixes stay unknown."""
    module = _load_site_generator()
    rows = [
        {
            "status": "success",
            "country": "Romania",
            "countryCode": "RO",
            "city": "Bucharest",
            "isp": "M247",
            "lat": 44.43,
            "lon": 26.1,
            "query": "203.0.113.10",
        },
        {"status": "fail", "query": "104.21.12.34"},
    ]
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(rows).encode("utf-8")
    anycast = _proxy(
        server="104.21.12.34", geo_source="anycast-provider", carrier="Cloudflare Anycast"
    )
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_GEOIP_DISABLE", None)
        with mock.patch.object(module.urllib.request, "urlopen", return_value=response):
            records, translation = module._geoip_batch_lookup(["203.0.113.10", "104.21.12.34"])
            assert set(translation) == {"203.0.113.10", "104.21.12.34"}
            proxies = module.enrich_proxies_with_geoip([_proxy(), anycast])
    enriched = proxies[0]
    assert enriched["country"] == "RO"
    assert enriched["country_name"] == "Romania"
    assert enriched["carrier"] == "M247"
    assert enriched["city"] == "Bucharest"
    assert enriched["latitude"] == 44.43
    assert enriched["longitude"] == 26.1
    assert enriched["geo_source"] == "ip-api"
    assert enriched["geo_verified"] is True
    assert proxies[1]["country"] == "ZZ"
    assert proxies[1]["carrier"] == "Cloudflare Anycast"
    assert proxies[1]["geo_source"] == "anycast-provider"
    assert proxies[1]["geo_verified"] is False


def test_tcp_probe_records_measured_latency_and_failure() -> None:
    """TCP probes set latency in milliseconds on success and probe_ok=False on failure."""
    module = _load_site_generator()
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_PROBE_DISABLE", None)
        with mock.patch.object(module.socket, "create_connection", side_effect=OSError("refused")):
            failed = module.probe_tcp_latency([_proxy(server="198.51.100.2")])
        assert failed[0]["probe_ok"] is False
        assert failed[0].get("latency") is None
        with mock.patch.object(module.socket, "create_connection", return_value=mock.MagicMock()):
            with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 0.042]):
                succeeded = module.probe_tcp_latency([_proxy(server="198.51.100.1")])
    assert succeeded[0]["probe_ok"] is True
    assert succeeded[0]["latency"] == 42


def test_catalog_tags_keep_client_configs_out_of_subscription_feeds() -> None:
    """Complete client configs are profile imports; node feeds stay subscription-usable."""
    module = _load_site_generator()
    singbox_type, singbox_tags, singbox_desc = module._infer_tags_and_type(
        Path("release/all_sources_npvt_singbox.json"), "release"
    )
    assert singbox_type == "SINGBOX"
    assert "subscription" not in singbox_tags
    assert "not a subscription" in singbox_desc
    xray_type, xray_tags, _ = module._infer_tags_and_type(
        Path("release/all_sources_npvt_xray.json"), "release"
    )
    assert xray_type == "XRAY"
    assert "subscription" not in xray_tags
    nekobox_type, nekobox_tags, _ = module._infer_tags_and_type(
        Path("release/all_sources_npvt_nekobox.json"), "release"
    )
    assert nekobox_type == "NEKOBOX"
    assert "subscription" in nekobox_tags
    assert "json-nodes" in nekobox_tags
    raw_type, raw_tags, _ = module._infer_tags_and_type(
        Path("release/all_sources_npvt_raw.txt"), "release"
    )
    assert raw_type == "TXT"
    assert "subscription" not in raw_tags
    npvt_type, npvt_tags, _ = module._infer_tags_and_type(
        Path("release/all_sources.npvt.json"), "release"
    )
    assert npvt_type == "NPVT"
    assert "subscription" in npvt_tags


def test_frontend_feeds_filter_includes_json_node_feeds() -> None:
    """The subscriptions filter offers tagged JSON node feeds; client configs are a separate bucket."""
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    # The catalog tags NEKOBOX JSON node feeds as "subscription", and the
    # subscriptions filter admits anything carrying that tag.
    subs = application.split('filter === "SUBSCRIPTIONS"')[1].split("} else if")[0]
    assert 'f.tags.includes("subscription")' in subs
    # A JSON node feed is not a client config: the config bucket lists clients only.
    configs = application.split('filter === "CONFIGS"')[1].split("} else if")[0]
    assert "NEKOBOX" not in configs


def test_unresolvable_servers_are_dropped_but_tcp_failures_kept() -> None:
    """Only DNS-dead nodes are dropped; a refused connect must survive."""
    module = _load_site_generator()
    live_literal = _proxy(server="203.0.113.10")
    dead_hostname = _proxy(server="does-not-resolve.invalid")
    refused = _proxy(server="198.51.100.7")
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_KEEP_UNRESOLVED", None)
        # A refused TCP connect is NOT proof of death: the host exists.
        with mock.patch.object(module.socket, "create_connection", side_effect=OSError("refused")):
            survivors = module.drop_unreachable_proxies([live_literal, dead_hostname, refused])
    servers = [proxy["server"] for proxy in survivors]
    assert "203.0.113.10" in servers      # literal IP needs no DNS
    assert "198.51.100.7" in servers       # resolvable, connect refused -> kept
    assert "does-not-resolve.invalid" not in servers


def test_unresolved_filter_can_be_disabled() -> None:
    module = _load_site_generator()
    with mock.patch.dict(os.environ, {"HUNTX_KEEP_UNRESOLVED": "1"}):
        survivors = module.drop_unreachable_proxies([_proxy(server="nx.invalid")])
    assert len(survivors) == 1


def test_hostname_geo_resolution_feed_unknown_hosts_to_geoip() -> None:
    """Hostnames must be translated to IPs so the GeoIP batch can locate them."""
    module = _load_site_generator()
    with mock.patch.object(module.socket, "gethostbyname", return_value="192.0.2.55"):
        resolved = module._resolve_hostnames(["203.0.113.10", "de-1.example.com"])
    assert resolved == ["203.0.113.10", "192.0.2.55"]


def test_carrier_panel_reports_all_failed_probes_without_bogus_latency() -> None:
    """A carrier whose every probe failed must not synthesize a 0ms average."""
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    # The average is computed only from successful probes; an empty ping
    # list yields no latency at all rather than a synthesized 0ms average.
    assert "const hasProbe = c.pings.length > 0" in application
    assert "c.pings.reduce((a, b) => a + b, 0) / c.pings.length) : null" in application


def test_health_grade_combines_probe_latency_and_security() -> None:
    """Reachability, latency band, and transport security form one letter grade."""
    module = _load_site_generator()
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_HEALTH_DISABLE", None)
        fast = module.grade_proxy_health([_proxy(latency=20, probe_ok=True, security_grade="A+")])[0]
        slow = module.grade_proxy_health([_proxy(latency=250, probe_ok=True, security_grade="A+")])[0]
        down = module.grade_proxy_health([_proxy(latency=None, probe_ok=False, security_grade="A+")])[0]
    assert fast["health_grade"] == "A+"
    assert fast["health_status"] == "Reachable at publish"
    assert fast["latency_grade"] == "A+"
    assert slow["health_grade"] == "C+"
    assert down["health_grade"] == "F"
    assert down["health_status"] == "TCP unreachable at publish"
    assert down["latency_grade"] is None


def test_health_grade_can_be_disabled() -> None:
    module = _load_site_generator()
    with mock.patch.dict(os.environ, {"HUNTX_HEALTH_DISABLE": "1"}):
        untouched = module.grade_proxy_health([_proxy(latency=20, probe_ok=True)])[0]
    assert "health_grade" not in untouched
    assert "health_status" not in untouched
    assert untouched["latency"] == 20


def test_reachable_unreachable_proxies_are_never_invented() -> None:
    """A negative, boolean, or NaN latency yields no latency band."""
    module = _load_site_generator()
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_HEALTH_DISABLE", None)
        for bogus in (-5, True, float("nan"), None):
            graded = module.grade_proxy_health([_proxy(latency=bogus, probe_ok=True)])[0]
            assert graded["latency_grade"] is None
            assert graded["health_grade"] is None


def test_remark_marks_unreachable_nodes_as_failed() -> None:
    """A probe failure must override any declared health grade."""
    from huntx.formats.npvt import format_enriched_remark
    down = format_enriched_remark("vless://x@h:443", {}, {"country": "DE", "health_grade": "A+", "probe_ok": False})
    assert "⭐F" in down
    assert "⭐A+" not in down
    up = format_enriched_remark("vless://x@h:443", {}, {"country": "DE", "health_grade": "A"})
    assert "⭐A" in up


def test_geoip_enrichment_matches_hostname_nodes_through_resolved_ip() -> None:
    """A hostname server must receive the geo record of the IP it resolved to."""
    module = _load_site_generator()
    hostname = "de-1.example.com"
    resolved_ip = "192.0.2.55"
    records = {
        resolved_ip: {
            "country": "DE",
            "carrier": "Hetzner",
            "geo_source": "ip-api",
            "geo_verified": True,
            "country_name": "Germany",
        }
    }
    translation = {hostname: resolved_ip}
    with mock.patch.dict(os.environ):
        os.environ.pop("HUNTX_GEOIP_DISABLE", None)
        with mock.patch.object(module, "_resolve_hostnames", return_value=[resolved_ip]):
            with mock.patch.object(module, "_geoip_batch_lookup", return_value=(records, translation)):
                proxies = module.enrich_proxies_with_geoip([_proxy(server=hostname)])
    assert proxies[0]["country"] == "DE"
    assert proxies[0]["carrier"] == "Hetzner"
    assert proxies[0]["geo_source"] == "ip-api"
    assert proxies[0]["geo_verified"] is True


def test_frontend_uses_only_canonical_product_artifact_names() -> None:
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")

    for canonical in (
        "all_sources_npvt_decoded.json",
        "all_sources_npvt_nekobox.json",
        "all_sources_npvt_raw.txt",
        "all_sources_npvt_singbox.json",
        "all_sources_npvt_xray.json",
    ):
        assert canonical in application

    for stale in (
        "all_sources.npvt.decoded.json",
        "all_sources.npvt.nekobox.json",
        "all_sources.npvt.raw.txt",
        "all_sources.npvt.singbox.json",
        "all_sources.npvt.xray.json",
        "v2ray_test_config.json",
    ):
        assert stale not in application

    assert "NekoBox Node Subscription" in application
    assert "imports as one profile" in application
