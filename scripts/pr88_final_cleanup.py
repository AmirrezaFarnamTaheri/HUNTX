from pathlib import Path
import re


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 regex match, found {count}")
    p.write_text(updated, encoding="utf-8")


replace_once(
    "docs/assets/js/globe.js",
    '  const sourceHubs = (customHubs && Array.isArray(customHubs) && customHubs.length > 0)\n    ? customHubs\n    : DEFAULT_HUBS;',
    '  // An explicit empty hub list is authoritative. Only null/omitted input opts\n'
    '  // into demo hubs; the dashboard passes [] when no evidence-backed hubs exist.\n'
    '  const sourceHubs = Array.isArray(customHubs) ? customHubs : DEFAULT_HUBS;',
    "preserve explicit empty globe hubs",
)

regex_once(
    "docs/assets/js/app.js",
    r'''  \} else if \(addr\.startsWith\("162\.159\."\) \|\| addr\.startsWith\("172\.67\."\) \|\| addr\.startsWith\("104\.18\."\) \|\| addr\.startsWith\("104\.19\."\) \|\| addr\.startsWith\("104\.21\."\) \|\| addr\.startsWith\("104\.16\."\) \|\| addr\.startsWith\("172\.64\."\)\) \{\n    const parts = addr\.split\("\."\);\n    const oct3 = parts\.length >= 3 && !isNaN\(Number\(parts\[2\]\)\) \? Number\(parts\[2\]\) : 0;\n    const cfRoutes = \[[\s\S]*?\n    const \[c, car\] = cfRoutes\[oct3 % cfRoutes\.length\];\n    country = c;\n    carrier = car;''',
    '''  } else if (addr.startsWith("162.159.") || addr.startsWith("172.67.") || addr.startsWith("104.18.") || addr.startsWith("104.19.") || addr.startsWith("104.21.") || addr.startsWith("104.16.") || addr.startsWith("172.64.")) {
    // Cloudflare addresses are anycast. The address alone cannot truthfully
    // identify a country or city, so retain provider evidence without inventing geography.
    return {
      country: "ZZ",
      country_name: "Unknown",
      flag: "🌐",
      carrier: "Cloudflare Anycast",
      org: "Cloudflare",
      city: "Unknown",
      latitude: null,
      longitude: null,
      geo_source: "anycast-provider",
      geo_verified: false
    };''',
    "remove arbitrary Cloudflare city routing",
)

regex_once(
    "scripts/generate_site_data.py",
    r'''    elif addr\.startswith\(\("162\.159\.", "172\.67\.", "104\.18\.", "104\.19\.", "104\.21\.", "104\.16\.", "172\.64\."\)\):\n        oct3 = int\(addr\.split\("\."\)\[2\]\) if len\(addr\.split\("\."\)\) >= 3 and addr\.split\("\."\)\[2\]\.isdigit\(\) else 0\n        cf_routes = \[[\s\S]*?\n        country, carrier = cf_routes\[oct3 % len\(cf_routes\)\]''',
    '''    elif addr.startswith(("162.159.", "172.67.", "104.18.", "104.19.", "104.21.", "104.16.", "172.64.")):
        # Cloudflare IPs are anycast; provider identity is evidence, location is not.
        return {
            "country": "ZZ",
            "country_name": "Unknown",
            "flag": "🌐",
            "carrier": "Cloudflare Anycast",
            "org": "Cloudflare",
            "city": "Unknown",
            "latitude": None,
            "longitude": None,
            "geo_source": "anycast-provider",
            "geo_verified": False,
        }''',
    "remove arbitrary Cloudflare city routing in generator",
)

replace_once(
    "scripts/generate_site_data.py",
    '    country = "US"\n    carrier = "Direct Carrier"',
    '    country = None\n    carrier = None',
    "truthful geo defaults",
)

replace_once(
    "docs/assets/js/i18n.js",
    '    const regionsBadgeMatch = source.match(/^(\\d+)\\s+REGIONS$/i);',
    '    const regionsBadgeMatch = source.match(/^(\\d+)\\s+REGIONS$/);',
    "exact uppercase region badge",
)

js_docs = [
    (
        "docs/assets/js/app.js",
        'export function resolveGeoAndCarrier(address, sni = "", host = "") {',
        '/** Infer coarse provider/region metadata without fabricating unknown or anycast locations. */\nexport function resolveGeoAndCarrier(address, sni = "", host = "") {',
    ),
    (
        "docs/assets/js/app.js",
        'export function healthForLatency(ping) {',
        '/** Map a measured latency value to the canonical dashboard health grade. */\nexport function healthForLatency(ping) {',
    ),
    (
        "docs/assets/js/app.js",
        'export function securityGrade(security) {',
        '/** Grade transport security independently from latency health. */\nexport function securityGrade(security) {',
    ),
    (
        "docs/assets/js/app.js",
        'export function clusterGlobeHubs(proxies) {',
        '/** Cluster only evidence-backed proxy coordinates into globe hubs. */\nexport function clusterGlobeHubs(proxies) {',
    ),
    (
        "docs/assets/js/globe.js",
        'export function initTelemetryGlobe(canvasId, onNodeSelect, customHubs = null, options = {}) {',
        '/** Mount the telemetry globe with explicit touch-gating and evidence-backed hubs. */\nexport function initTelemetryGlobe(canvasId, onNodeSelect, customHubs = null, options = {}) {',
    ),
]
for path, old, new in js_docs:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    marker = new.split("\n", 1)[0]
    if marker not in text:
        if text.count(old) != 1:
            raise SystemExit(f"documentation target missing: {path} {old}")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

py_docs = {
    "scripts/generate_site_data.py": {
        "def _generated_at() -> str:": '    """Return the reproducible generation timestamp when configured, otherwise UTC now."""',
        "def _format_size(size_bytes: int) -> str:": '    """Format a byte count for compact dashboard display."""',
        "def _sha256(path: Path) -> str:": '    """Compute the SHA-256 digest of a generated artifact."""',
        "def _infer_media_type(path: Path) -> str:": '    """Infer the published MIME type from HUNTX artifact naming conventions."""',
        "def _infer_tags_and_type(path: Path, section: str) -> tuple[str, list[str], str]:": '    """Derive dashboard type, tags, and description for a published artifact."""',
        "def _country_flag(code: str) -> str:": '    """Render a two-letter country code as an emoji flag when possible."""',
        'def resolve_geo_and_carrier(address: str, sni: str = "", host: str = "") -> dict:': '    """Infer coarse metadata while keeping unknown and anycast geography explicitly unknown."""',
        "def _parse_proxy_uri(uri: str) -> dict | None:": '    """Parse one supported proxy URI into normalized connection metadata."""',
        "def parse_production_proxies() -> list[dict]:": '    """Load and normalize the production proxy snapshot for static publishing."""',
        "def compute_aggregate_stats(proxies: list[dict], catalog: dict) -> dict:": '    """Compute aggregate dashboard statistics without inventing unavailable measurements."""',
        "def generate_all() -> None:": '    """Generate the static artifact catalog and frontend data module."""',
    },
    "scripts/update_frontend.py": {
        "def build_index_content(root: Path | None = None) -> str:": '    """Render the dashboard index from the canonical template and current counts."""',
        "def write_index(root: Path | None = None) -> None:": '    """Write the rendered dashboard index to docs/index.html."""',
    },
}
for path, docs in py_docs.items():
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    for signature, doc in docs.items():
        target = signature + "\n"
        documented = signature + "\n" + doc + "\n"
        if documented in text:
            continue
        if text.count(target) != 1:
            raise SystemExit(f"python documentation target missing: {path} {signature}")
        text = text.replace(target, documented, 1)
    p.write_text(text, encoding="utf-8")

runtime = Path("tests/frontend_runtime.test.mjs")
runtime_text = runtime.read_text(encoding="utf-8")
anchor = '''test("unknown endpoints do not receive fabricated geography", () => {
  const geo = resolveGeoAndCarrier("203.0.113.199", "", "");
  assert.equal(geo.country, "ZZ");
  assert.equal(geo.carrier, "Unverified");
  assert.equal(geo.latitude, null);
  assert.equal(geo.longitude, null);
  assert.equal(geo.geo_source, "unknown");
  assert.equal(geo.geo_verified, false);
});
'''
addition = anchor + '''
test("Cloudflare anycast keeps provider evidence without invented geography", () => {
  const geo = resolveGeoAndCarrier("104.21.12.34", "", "");
  assert.equal(geo.country, "ZZ");
  assert.equal(geo.carrier, "Cloudflare Anycast");
  assert.equal(geo.org, "Cloudflare");
  assert.equal(geo.latitude, null);
  assert.equal(geo.longitude, null);
  assert.equal(geo.geo_source, "anycast-provider");
});
'''
if 'test("Cloudflare anycast keeps provider evidence without invented geography"' not in runtime_text:
    if runtime_text.count(anchor) != 1:
        raise SystemExit("runtime geo test anchor missing")
    runtime_text = runtime_text.replace(anchor, addition, 1)

old_assert = '  assert.match(source, /clearTimeout\\(touchInactivityTimer\\)/);\n'
new_assert = (
    old_assert
    + '  assert.match(source, /const sourceHubs = Array\\.isArray\\(customHubs\\) \\? customHubs : DEFAULT_HUBS/);\n'
    + '  assert.doesNotMatch(source, /customHubs\\.length > 0/);\n'
)
if 'assert.doesNotMatch(source, /customHubs\\.length > 0/);' not in runtime_text:
    if runtime_text.count(old_assert) != 1:
        raise SystemExit("globe source assertion anchor missing")
    runtime_text = runtime_text.replace(old_assert, new_assert, 1)
runtime.write_text(runtime_text, encoding="utf-8")

delivery = Path("tests/test_frontend_delivery.py")
delivery_text = delivery.read_text(encoding="utf-8")
if "def test_cloudflare_anycast_geo_is_not_fabricated()" not in delivery_text:
    delivery_text += '''

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
'''
    delivery.write_text(delivery_text, encoding="utf-8")
