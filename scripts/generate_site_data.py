import concurrent.futures
import hashlib
import json
import math
import mimetypes
import os
import shutil
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _generated_at() -> str:
    """Return the reproducible generation timestamp when configured, otherwise UTC now."""
    override = os.environ.get("HUNTX_GENERATED_AT", "").strip()
    if override:
        return override
    return datetime.now(timezone.utc).isoformat()


REPO_ROOT = Path(__file__).resolve().parents[1]


def _configured_sources_count():
    """Count source entries actually configured for production ingestion.

    Returns None when the config cannot be parsed so the UI can show an
    honest dash instead of an invented number.
    """
    text = CONFIG_PROD_FILE.read_text(encoding="utf-8") if CONFIG_PROD_FILE.exists() else ""
    if not text:
        return None
    try:
        import yaml

        config = yaml.safe_load(text) or {}
        sources = config.get("sources") or []
        return len(sources) or None
    except Exception:
        in_sources = False
        count = 0
        for line in text.splitlines():
            if line.startswith("sources:"):
                in_sources = True
                continue
            if in_sources and line and not line[0].isspace():
                break
            if in_sources and line.lstrip().startswith("- "):
                count += 1
        return count or None


OUTPUTS_DIR = REPO_ROOT / "outputs"
OUTPUTS_DEV_DIR = REPO_ROOT / "outputs_dev"
DOCS_DIR = REPO_ROOT / "docs"
ARTIFACTS_DIR = DOCS_DIR / "artifacts"
CATALOG_FILE = DOCS_DIR / "catalog.json"
DATA_JS_FILE = DOCS_DIR / "assets" / "js" / "data.js"
CONFIG_PROD_FILE = REPO_ROOT / "configs" / "config.prod.yaml"
# The one classification table for both catalog generators: the Go site tool
# embeds it and this module reads it, so a filename is described identically
# whichever generator catalogs it.
ARTIFACT_FORMATS_FILE = REPO_ROOT / "internal" / "sitegen" / "artifact_formats.json"
# go:embed cannot reference files above the package directory, so the table
# lives with the Go tool that compiles it in; this module reads the same file.

# Public products are intentionally narrower than the generated artifact tree.
# Compatibility variants remain copied and directly addressable, but are not
# presented as separate final products in the dashboard.
FRONTEND_RELEASE_PRODUCTS = {
    "all_sources_npvt_decoded.json",
    "all_sources_npvt_nekobox.json",
    "all_sources_npvt_raw.txt",
    "all_sources_npvt_singbox.json",
    "all_sources_npvt_xray.json",
}
FRONTEND_DEV_PRODUCTS = {"proxies.json"}


def _is_frontend_product(section: str, filename: str) -> bool:
    if section == "release":
        return filename in FRONTEND_RELEASE_PRODUCTS
    if section == "dev":
        return filename in FRONTEND_DEV_PRODUCTS
    return False


def _format_size(size_bytes: int) -> str:
    """Format a byte count for compact dashboard display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _sha256(path: Path) -> str:
    """Compute the SHA-256 digest of a generated artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_media_type(path: Path) -> str:
    """Infer the published MIME type from HUNTX artifact naming conventions."""
    name = path.name.lower()
    if name.endswith(".json") or ".json" in name:
        return "application/json"
    if name.endswith(".ovpn"):
        return "application/x-openvpn-profile"
    if name.endswith(".npvt"):
        return "application/x-npvt-subscription"
    if name.endswith(".b64sub") or name.endswith(".txt") or name.endswith(".md"):
        return "text/plain"
    if name.endswith(".opaque_bundle"):
        return "application/octet-stream"
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "application/octet-stream"


ARTIFACT_FORMATS_CACHE: dict[str, dict] = {}


def _load_artifact_formats() -> dict:
    """Read and cache the shared classification table.

    The Go site generator embeds the same file, so both generators describe
    one filename identically. A malformed table never breaks generation: the
    fallback is the previous extension-only typing.
    """
    if "table" not in ARTIFACT_FORMATS_CACHE:
        try:
            payload = json.loads(ARTIFACT_FORMATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            payload = {"sections": {}}
        ARTIFACT_FORMATS_CACHE["table"] = payload if isinstance(payload, dict) else {}
    return ARTIFACT_FORMATS_CACHE["table"]


def _rule_matches(name: str, rule: dict) -> bool:
    """Apply one classification rule's predicate to a lowercased filename.

    Mirrors internal/sitegen ruleMatches, so one table classifies the same
    way in the Go publish tool and here. An empty or non-string predicate
    never matches: a rule that matched every filename would make the
    table's ordered precedence meaningless.
    """
    match = rule.get("match") or {}
    kind = match.get("kind")
    value = match.get("value")

    def scalar(candidate: object) -> str | None:
        return candidate if isinstance(candidate, str) and candidate else None

    def list_of_strings(candidate: object) -> list[str]:
        if not isinstance(candidate, list):
            return []
        return [v for v in candidate if isinstance(v, str) and v]

    if kind == "contains":
        wanted = scalar(value)
        return wanted is not None and wanted in name
    if kind == "contains_any":
        return any(v in name for v in list_of_strings(value))
    if kind == "endswith":
        wanted = scalar(value)
        return wanted is not None and name.endswith(wanted)
    if kind == "endswith_any":
        return any(name.endswith(v) for v in list_of_strings(value))
    if kind == "starts_with":
        wanted = scalar(value)
        return wanted is not None and name.startswith(wanted)
    if kind == "equals":
        wanted = scalar(value)
        return wanted is not None and name == wanted
    return False


def _infer_tags_and_type(path: Path, section: str) -> tuple[str, list[str], str]:
    """Derive dashboard type, tags, and description for a published artifact.

    Rules come from internal/sitegen/artifact_formats.json, evaluated in file
    order so
    the first match wins. Precedence matters: ``all_sources.npvt.singbox.json``
    is a Sing-box profile, not an NPVT feed.
    """
    name = path.name.lower()
    section_table = (_load_artifact_formats().get("sections") or {}).get(section) or {}
    ext = path.suffix.lstrip(".").upper() or "FILE"
    tags = list(section_table.get("base_tags") or [section])
    desc = str(section_table.get("default_description") or "")

    for rule in section_table.get("rules") or []:
        if not _rule_matches(name, rule):
            continue
        kind = rule.get("type") or "from_extension"
        if kind == "from_extension":
            ext = path.suffix.lstrip(".").upper()
        else:
            ext = str(kind)
        tags.extend(rule.get("tags") or [])
        description = str(rule.get("description") or "")
        if description:
            desc = description.replace("{filename}", path.name)
        break

    return ext, tags, desc


COUNTRY_NAMES = {
    "DE": "Germany", "NL": "Netherlands", "US": "United States", "GB": "United Kingdom",
    "FR": "France", "FI": "Finland", "SG": "Singapore", "JP": "Japan", "KR": "South Korea",
    "HK": "Hong Kong", "TR": "Turkey", "SE": "Sweden", "CH": "Switzerland", "CA": "Canada",
    "IR": "Iran", "RU": "Russia", "AU": "Australia", "BR": "Brazil", "ZA": "South Africa",
    "IT": "Italy", "ES": "Spain", "AE": "UAE", "IN": "India", "TW": "Taiwan", "UA": "Ukraine",
    "IE": "Ireland"
}


def _country_flag(code: str) -> str:
    """Render a two-letter country code as an emoji flag when possible."""
    if not code or len(code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())


GEO_COORDINATES = {
    "DE": (50.1109, 8.6821, "Frankfurt Hub"),
    "NL": (52.3676, 4.9041, "Amsterdam Hub"),
    "FI": (60.1699, 24.9384, "Helsinki Hub"),
    "US": (37.7749, -122.4194, "Silicon Valley"),
    "FR": (48.8566, 2.3522, "Paris Hub"),
    "GB": (51.5074, -0.1278, "London Edge"),
    "RU": (55.7558, 37.6173, "Moscow Hub"),
    "SG": (1.3521, 103.8198, "Singapore Hub"),
    "JP": (35.6762, 139.6503, "Tokyo Hub"),
    "KR": (37.5665, 126.9780, "Seoul Hub"),
    "HK": (22.3193, 114.1694, "Hong Kong Edge"),
    "CH": (47.3769, 8.5417, "Zurich Edge"),
    "SE": (59.3293, 18.0686, "Stockholm Hub"),
    "IR": (35.6892, 51.3890, "Tehran Edge"),
    "TR": (41.0082, 28.9784, "Istanbul Hub"),
    "CA": (43.6532, -79.3832, "Toronto Edge"),
    "AU": (-33.8688, 151.2093, "Sydney Hub"),
    "BR": (-23.5505, -46.6333, "São Paulo Hub"),
    "ZA": (-26.2041, 28.0473, "Johannesburg Edge"),
    "IN": (19.0760, 72.8777, "Mumbai Hub"),
    "TW": (25.0330, 121.5654, "Taipei Edge"),
    "UA": (50.4501, 30.5234, "Kyiv Edge"),
    "IE": (53.3498, -6.2603, "Dublin Edge"),
}


def resolve_geo_and_carrier(address: str, sni: str = "", host: str = "") -> dict:
    """Infer coarse metadata while keeping unknown and anycast geography explicitly unknown."""
    addr = (address or "").strip().lower()
    sni_lower = (sni or "").strip().lower()
    host_lower = (host or "").strip().lower()
    full = f"{addr} {sni_lower} {host_lower}"

    country = None
    carrier = None

    # 1. Explicit domain TLDs & contextual keywords
    if ".ir" in addr or "iran" in full or "tehran" in full or "soundfiy" in full or "zula.ir" in full:
        country, carrier = "IR", "MCI / Irancell"
    elif ".ua" in addr or "ukraine" in full:
        country, carrier = "UA", "Kyivstar / Datagroup"
    elif ".in" in addr or "india" in full:
        country, carrier = "IN", "Jio / Bharti Airtel"
    elif "taipei" in full or ".tw" in addr or "taiwan" in full:
        country, carrier = "TW", "Chunghwa Telecom"
    elif ".de" in addr or "germany" in full or "frankfurt" in full:
        country, carrier = "DE", "Hetzner Cloud"
    elif ".nl" in addr or "amsterdam" in full or "serverius" in full or "sellflow" in full:
        country, carrier = "NL", "Serverius / NL"
    elif ".fi" in addr or "helsinki" in full or "fastly" in full:
        country, carrier = "FI", "Hetzner Online"
    elif ".fr" in addr or "paris" in full:
        country, carrier = "FR", "OVHcloud FR"
    elif ".ru" in addr or "moscow" in full or "rtqa.ru" in full or "vdsina" in full:
        country, carrier = "RU", "Rostelecom / Selectel"
    elif ".sg" in addr or "singapore" in full or "zenlayer" in full:
        country, carrier = "SG", "Zenlayer SG"
    elif ".jp" in addr or "tokyo" in full or "japan" in full:
        country, carrier = "JP", "AWS Tokyo"
    elif ".kr" in addr or "seoul" in full or "korea" in full:
        country, carrier = "KR", "KT Corp"
    elif ".hk" in addr or "hongkong" in full or "aliyun" in full:
        country, carrier = "HK", "Alibaba Cloud HK"
    elif ".tr" in addr or "istanbul" in full or "turkey" in full or "tr1-" in full:
        country, carrier = "TR", "Turkcell / Superonline"
    elif ".ch" in addr or "zurich" in full or "swiss" in full or ".cloudns.ch" in addr:
        country, carrier = "CH", "Swisscom Zurich"
    elif ".uk" in addr or ".co.uk" in addr or ".gb" in addr or "london" in full:
        country, carrier = "GB", "Virgin Media UK"
    elif ".ca" in addr or "toronto" in full or "canada" in full:
        country, carrier = "CA", "OVH Canada"
    elif ".se" in addr or "stockholm" in full or "sweden" in full:
        country, carrier = "SE", "Telia Sweden"
    # 2. IP Subnet & Cloud Provider Network Routing
    elif addr.startswith("188.114."):
        country, carrier = "NL", "Cloudflare Amsterdam Edge"
    elif addr.startswith(("162.159.", "172.67.", "104.18.", "104.19.", "104.21.", "104.16.", "172.64.")):
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
        }
    elif addr.startswith(("47.243.", "8.210.", "8.217.")):
        country, carrier = "HK", "Alibaba Cloud HK"
    elif addr.startswith("51.79."):
        country, carrier = "SG", "OVHcloud Singapore"
    elif addr.startswith(("57.129.", "57.131.", "54.36.")):
        country, carrier = "FR", "OVHcloud France"
    elif addr.startswith(("15.237.", "15.235.")):
        country, carrier = "FR", "AWS Paris"
    elif addr.startswith("54.74."):
        country, carrier = "IE", "AWS Dublin"
    elif addr.startswith(("82.38.", "2.26.")):
        country, carrier = "GB", "Virgin Media UK"
    elif addr.startswith(("91.132.", "140.99.", "5.175.", "82.198.")):
        country, carrier = "DE", "Hetzner Cloud"
    elif addr.startswith(("95.81.", "86.107.")):
        country, carrier = "IR", "MCI / TCI Iran"
    elif addr.startswith(("194.87.", "62.182.", "195.133.", "31.133.")):
        country, carrier = "RU", "VDSina / Selectel"
    elif addr.startswith("199.232."):
        country, carrier = "FI", "Fastly Helsinki Edge"
    elif addr.startswith("150.40."):
        country, carrier = "JP", "AWS Tokyo"
    elif addr.startswith(("152.53.", "103.152.", "45.207.")):
        country, carrier = "SG", "Zenlayer Singapore"
    elif addr.startswith(("92.42.", "195.184.", "45.131.", "45.89.")):
        country, carrier = "NL", "Serverius Netherlands"
    elif addr.startswith(("69.63.", "192.227.", "167.233.", "166.62.", "209.206.")):
        country, carrier = "US", "AWS North America"
    elif addr.startswith("210.3."):
        country, carrier = "HK", "HKBN Hong Kong"
    else:
        return {
            "country": "ZZ",
            "country_name": "Unknown",
            "flag": "🌐",
            "carrier": "Unverified",
            "org": "Unverified",
            "city": "Unknown",
            "latitude": None,
            "longitude": None,
            "geo_source": "unknown",
            "geo_verified": False,
        }

    lat, lon, hub_name = GEO_COORDINATES[country]
    country_name = COUNTRY_NAMES.get(country, "Unknown")
    flag = _country_flag(country)

    return {
        "country": country,
        "country_name": country_name,
        "flag": flag,
        "carrier": carrier,
        "org": carrier,
        "city": hub_name,
        "latitude": lat,
        "longitude": lon,
        "geo_source": "inferred",
        "geo_verified": False,
    }


GEOIP_BATCH_ENDPOINT = "http://ip-api.com/batch"
GEOIP_BATCH_SIZE = 100           # ip-api.com batch limit per request
GEOIP_BATCH_PAUSE_SECONDS = 4.2  # the free tier allows 15 batch requests per minute
GEOIP_MAX_BATCHES = 60


def _geoip_batch_lookup(addresses: list[str]) -> tuple[dict[str, dict], dict[str, str]]:
    """Resolve addresses against ip-api.com's free batch endpoint (no key).

    Returns the geo record keyed by the *queried* address plus the address
    translation used (hostname -> IP). Callers that own the original hostnames
    need both: ip-api answers with the literal it was handed, so a hostname
    node only matches when the translation is applied to its own server.
    An empty or partial result on any network/decode failure lets generation
    fall back to the offline heuristics instead of failing the run.
    """
    results: dict[str, dict] = {}
    queried: list[str] = []
    batches = 0
    retried = False
    for start in range(0, len(addresses), GEOIP_BATCH_SIZE):
        if batches >= GEOIP_MAX_BATCHES:
            break
        batches += 1
        chunk = addresses[start:start + GEOIP_BATCH_SIZE]
        queried.extend(chunk)
        payload = json.dumps(
            [{"query": address} for address in chunk]
        ).encode("utf-8")
        request = urllib.request.Request(
            GEOIP_BATCH_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A rate-limit reply is transient: back off once and retry the
            # same batch rather than silently dropping the remaining nodes.
            if exc.code != 429 or retried:
                return results, dict(zip(addresses, queried))
            retried = True
            time.sleep(GEOIP_BATCH_PAUSE_SECONDS * 2)
            batches -= 1  # do not spend the batch budget on the retry
            start -= GEOIP_BATCH_SIZE
            continue
        except Exception:
            return results, dict(zip(addresses, queried))
        if not isinstance(rows, list):
            return results, dict(zip(addresses, queried))
        for row in rows:
            if not isinstance(row, dict) or row.get("status") != "success":
                continue
            code = str(row.get("countryCode") or "").strip().upper()
            if len(code) != 2 or not code.isascii() or not code.isalpha():
                continue
            address = str(row.get("query") or "").strip()
            if not address:
                continue
            isp = str(row.get("isp") or "").strip() or "Unverified"
            latitude = row.get("lat")
            longitude = row.get("lon")
            results[address] = {
                "country": code,
                "country_name": str(row.get("country") or "").strip() or COUNTRY_NAMES.get(code, "Unknown"),
                "flag": _country_flag(code),
                "carrier": isp,
                "org": isp,
                "city": str(row.get("city") or "").strip() or "Unknown",
                "latitude": latitude if isinstance(latitude, (int, float)) else None,
                "longitude": longitude if isinstance(longitude, (int, float)) else None,
                "geo_source": "ip-api",
                "geo_verified": True,
            }
        if start + GEOIP_BATCH_SIZE < len(addresses):
            time.sleep(GEOIP_BATCH_PAUSE_SECONDS)

    translation = dict(zip(addresses, queried))
    return results, translation


def _resolve_hostnames(addresses: list[str]) -> list[str]:
    """Translate hostname servers to IPs so GeoIP can locate them.

    ip-api.com resolves literal addresses only, so a hostname like
    ``de-1.example.com`` would otherwise stay unknown. Bare IPs and any
    host that does not resolve pass through unchanged; a lookup miss
    never removes a node from the batch.
    """
    def _one(address: str) -> str:
        if not address:
            return address
        try:
            socket.inet_aton(address)
            return address  # already a literal IPv4 address
        except OSError:
            pass
        try:
            return socket.gethostbyname(address) or address
        except OSError:
            return address

    # Hostnames resolve in parallel: the sequential path spent most of the
    # publish window waiting on one DNS query at a time.
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_MAX_WORKERS) as executor:
        return list(executor.map(_one, addresses))


def enrich_proxies_with_geoip(proxies: list[dict]) -> list[dict]:
    """Enrich explicitly-unknown geography with measured GeoIP where reachable.

    Only nodes whose geography is still unknown are looked up: anycast
    prefixes stay deliberately unknown (a registered PoP location is not the
    node's location), and a network failure leaves the heuristic record in
    place instead of failing generation. Set ``HUNTX_GEOIP_DISABLE=1`` to skip
    the lookups entirely.
    """
    if os.environ.get("HUNTX_GEOIP_DISABLE", "").strip():
        return proxies
    unresolved_addresses: list[str] = []
    seen: set[str] = set()
    for proxy in proxies:
        if proxy.get("geo_source") != "unknown":
            continue
        address = str(proxy.get("server") or "").strip()
        if not address or address in seen:
            continue
        seen.add(address)
        unresolved_addresses.append(address)
    if not unresolved_addresses:
        return proxies
    queried_addresses = _resolve_hostnames(unresolved_addresses)
    resolved, translation = _geoip_batch_lookup(queried_addresses)
    if not resolved:
        return proxies
    for proxy in proxies:
        server = str(proxy.get("server") or "").strip()
        # ip-api answers with the literal it was asked about. A hostname node
        # was queried as its resolved IP, so match through that translation.
        record = resolved.get(translation.get(server, server))
        if record is not None:
            proxy.update(record)
    return proxies


def _parse_proxy_uri(uri: str) -> dict | None:
    """Parse one supported proxy URI into normalized connection metadata."""
    try:
        if not uri or "://" not in uri:
            return None
        scheme, rest = uri.split("://", 1)
        scheme = scheme.lower()
        tag = ""
        if "#" in rest:
            rest, tag = rest.split("#", 1)
            tag = urllib.parse.unquote(tag)

        query = {}
        if "?" in rest:
            rest, qstr = rest.split("?", 1)
            query = dict(urllib.parse.parse_qsl(qstr))

        user = ""
        addr_port = rest
        if "@" in rest:
            user, addr_port = rest.rsplit("@", 1)

        host = addr_port
        port = 443
        if ":" in addr_port:
            h, p = addr_port.rsplit(":", 1)
            host = h
            try:
                port = int(p)
            except Exception:
                port = 443

        return {
            "protocol": scheme,
            "address": host,
            "port": port,
            "tag": tag or f"{scheme}-{host}",
            "params": query,
            "raw": uri,
            "user": user
        }
    except Exception:
        return None


PROBE_TIMEOUT_SECONDS = 2.5
PROBE_MAX_WORKERS = 128


def probe_tcp_latency(proxies: list[dict]) -> list[dict]:
    """Measure TCP handshake latency per node from the publisher vantage.

    One shared connect attempt per unique (server, port): success sets latency
    in milliseconds, failure keeps latency None with ``probe_ok`` recording the
    outcome so the dashboard can separate failed probes from unmeasured nodes.
    Set ``HUNTX_PROBE_DISABLE=1`` to skip the probes entirely.
    """
    if os.environ.get("HUNTX_PROBE_DISABLE", "").strip():
        return proxies
    targets: dict[tuple[str, int], list[int]] = {}
    for idx, proxy in enumerate(proxies):
        server = str(proxy.get("server") or "").strip()
        port = proxy.get("port")
        if not server or not isinstance(port, int) or not 0 < port < 65536:
            continue
        targets.setdefault((server, port), []).append(idx)
    if not targets:
        return proxies

    def measure(target: tuple[str, int]) -> tuple[tuple[str, int], int | None]:
        server, port = target
        started = time.monotonic()
        try:
            with socket.create_connection((server, port), timeout=PROBE_TIMEOUT_SECONDS):
                return target, round((time.monotonic() - started) * 1000)
        except OSError:
            return target, None

    outcomes: dict[tuple[str, int], int | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_MAX_WORKERS) as executor:
        for target, latency_ms in executor.map(measure, targets):
            outcomes[target] = latency_ms
    for idx, proxy in enumerate(proxies):
        server = str(proxy.get("server") or "").strip()
        port = proxy.get("port")
        outcome = outcomes.get((server, port)) if isinstance(port, int) else None
        if outcome is None:
            proxy["probe_ok"] = False
        else:
            proxy["probe_ok"] = True
            proxy["latency"] = outcome
    return proxies


def drop_unreachable_proxies(proxies: list[dict]) -> list[dict]:
    """Drop proxies whose server has no resolvable address at all.

    A name that will not resolve is dead for every client on the internet, so
    it is removed instead of being published as a selectable node. TCP probes
    are deliberately NOT a drop criterion: a refused or timed-out connect from
    the publish vantage may only mean the host does not answer that vantage,
    while an unresolvable name means the node cannot work for anyone.
    Set ``HUNTX_KEEP_UNRESOLVED=1`` to keep every node regardless.
    """
    if os.environ.get("HUNTX_KEEP_UNRESOLVED", "").strip():
        return proxies
    resolvable: dict[str, bool] = {}

    def check(address: str) -> tuple[str, bool]:
        try:
            socket.inet_aton(address)
            return address, True  # a literal address needs no DNS
        except OSError:
            pass
        try:
            socket.gethostbyname(address)
            return address, True
        except OSError:
            return address, False

    unique_servers = []
    seen: set[str] = set()
    for proxy in proxies:
        address = str(proxy.get("server") or "").strip()
        if address and address not in seen:
            seen.add(address)
            unique_servers.append(address)
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_MAX_WORKERS) as executor:
        for address, ok in executor.map(check, unique_servers):
            resolvable[address] = ok
    survivors = [p for p in proxies if resolvable.get(str(p.get("server") or "").strip(), False)]
    return survivors


HEALTH_LATENCY_BANDS = ((28, "A+"), (45, "A"), (70, "B+"), (120, "B"), (220, "C+"))
HEALTH_SECURITY_GRADES = {"A+": 3, "A": 2, "B+": 1}


def _latency_grade(latency_ms: int | float | None) -> str | None:
    """Band a measured round trip; an unmeasured node gets no invented band."""
    if not isinstance(latency_ms, (int, float)) or isinstance(latency_ms, bool):
        return None
    if not math.isfinite(latency_ms) or latency_ms < 0:
        return None
    for ceiling, grade in HEALTH_LATENCY_BANDS:
        if latency_ms <= ceiling:
            return grade
    return "C"


def grade_proxy_health(proxies: list[dict]) -> list[dict]:
    """Attach per-node health metadata derived from the measured probe.

    Three signals are combined into one letter grade so the dashboard and the
    published remarks can describe a node without inventing measurements:
    reachability (``probe_ok``), latency band, and transport security. Nodes
    that were never probed stay explicitly ``unmeasured`` rather than being
    scored as slow. Set ``HUNTX_HEALTH_DISABLE=1`` to leave grades unset.
    """
    if os.environ.get("HUNTX_HEALTH_DISABLE", "").strip():
        return proxies
    for proxy in proxies:
        latency = proxy.get("latency")
        proxy["latency_grade"] = _latency_grade(latency)
        security_grade = str(proxy.get("security_grade") or "")
        if proxy.get("probe_ok") is not True:
            # An unreachable node is graded on the one signal that exists.
            proxy["health_grade"] = "F"
            proxy["health_status"] = "TCP unreachable at publish"
            continue
        if proxy["latency_grade"] is None:
            proxy["health_grade"] = None
            proxy["health_status"] = "Probed, latency unavailable"
            continue
        # Security only upgrades a reachable, fast node; it never rescues one.
        boost = HEALTH_SECURITY_GRADES.get(security_grade, 0)
        order = [grade for _, grade in HEALTH_LATENCY_BANDS] + ["C"]
        position = max(0, order.index(proxy["latency_grade"]) - (1 if boost == 3 else 0))
        proxy["health_grade"] = order[position]
        proxy["health_status"] = "Reachable at publish"
    return proxies


GOVERNED_PCA_WEIGHTS = {
    "reachability": 0.40,  # a node nothing can connect to ranks last regardless of speed
    "latency": 0.30,       # normalised against the fleet's own measured spread
    "security": 0.20,      # transport hardening, not a substitute for reachability
    "geo_verification": 0.10,  # measured geography over heuristic guesses
}
GOVERNED_PCA_VERSION = 1

_GRADE_ORDER = {g: i for i, g in enumerate(["A+", "A", "B+", "B", "C+", "C", "F"])}


def _pca_security_component(proxy: dict) -> float:
    """Map transport security onto a 0..1 scale."""
    grade = str(proxy.get("security_grade") or "")
    return {"A+": 1.0, "A": 0.7, "B+": 0.4}.get(grade, 0.2)


def _pca_latency_component(proxy: dict, floor: float, ceiling: float) -> float:
    """Invert latency onto 0..1, normalised by the fleet's own measured spread.

    A singleton fleet has no spread to normalise against, so a single node is
    scored perfectly on the one dimension it can demonstrate.
    """
    latency = proxy.get("latency")
    if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency is None:
        return 0.0
    if not math.isfinite(latency) or latency < 0:
        return 0.0
    if ceiling <= floor:
        return 1.0
    span = ceiling - floor
    return max(0.0, min(1.0, 1.0 - ((latency - floor) / span)))


def score_governed_pca(proxies: list[dict]) -> list[dict]:
    """Rank nodes on one governed composite of the measured telemetry signals.

    The weights are declared and versioned rather than fitted, so a score is
    comparable across runs and auditable: reachability dominates because a fast
    but dead node is worth less than a slow live one. Every component is
    derived from a measurement this pipeline actually took; a node with no
    measurement scores 0 on that component rather than an imputed average.
    Set ``HUNTX_PCA_DISABLE=1`` to leave scores unset.
    """
    if os.environ.get("HUNTX_PCA_DISABLE", "").strip():
        return proxies
    latencies = [
        p["latency"] for p in proxies
        if isinstance(p.get("latency"), (int, float)) and not isinstance(p["latency"], bool) and math.isfinite(p["latency"]) and p["latency"] >= 0
    ]
    floor = min(latencies) if latencies else 0.0
    ceiling = max(latencies) if latencies else 0.0
    for proxy in proxies:
        reachability = 1.0 if proxy.get("probe_ok") is True else 0.0
        latency_score = _pca_latency_component(proxy, floor, ceiling)
        security = _pca_security_component(proxy)
        geo = 1.0 if proxy.get("geo_verified") is True else 0.0
        proxy["pca_score"] = round(
            GOVERNED_PCA_WEIGHTS["reachability"] * reachability
            + GOVERNED_PCA_WEIGHTS["latency"] * latency_score
            + GOVERNED_PCA_WEIGHTS["security"] * security
            + GOVERNED_PCA_WEIGHTS["geo_verification"] * geo,
            3,
        )
        proxy["pca_version"] = GOVERNED_PCA_VERSION
    return proxies


def parse_production_proxies() -> list[dict]:
    """Load and normalize the production proxy snapshot for static publishing."""
    raw_nodes: list[dict] = []

    # 1. Prefer the canonical production derivative; dotted naming is legacy.
    decoded_file = OUTPUTS_DIR / "all_sources_npvt_decoded.json"
    if not decoded_file.exists():
        decoded_file = OUTPUTS_DIR / "all_sources.npvt.decoded.json"

    if decoded_file.exists():
        try:
            data = json.loads(decoded_file.read_text(encoding="utf-8"))
            for entry in data.get("entries", []):
                raw_nodes.append({
                    "protocol": (entry.get("protocol") or "vless").lower(),
                    "address": entry.get("address") or "",
                    "port": entry.get("port") or 443,
                    "tag": entry.get("tag") or "",
                    "params": entry.get("params") or {},
                    "raw": entry.get("raw") or "",
                    "user": entry.get("user") or entry.get("password") or ""
                })
        except Exception:
            pass

    # 2. Production Outbound Configurations: v2ray_test_config.json (742 outbounds)
    v2ray_file = OUTPUTS_DIR / "v2ray_test_config.json"
    if v2ray_file.exists():
        try:
            vdata = json.loads(v2ray_file.read_text(encoding="utf-8"))
            for ob in vdata.get("outbounds", []):
                proto = ob.get("protocol", "vmess").lower()
                settings = ob.get("settings", {})
                stream = ob.get("streamSettings", {})
                tag = ob.get("tag") or f"{proto}-{len(raw_nodes)+1}"
                addr, port, user = "", 443, ""
                vnext = settings.get("vnext", [])
                if vnext:
                    addr = vnext[0].get("address", "")
                    port = vnext[0].get("port", 443)
                    users = vnext[0].get("users", [])
                    if users:
                        user = users[0].get("id", "")
                net = stream.get("network", "tcp")
                sec = stream.get("security", "none")
                raw_nodes.append({
                    "protocol": proto,
                    "address": addr,
                    "port": port,
                    "tag": tag,
                    "params": {"type": net, "security": sec},
                    "raw": f"{proto}://{user}@{addr}:{port}?type={net}&security={sec}#{tag}",
                    "user": user
                })
        except Exception:
            pass

    # 3. Protocol Diversity from Dev Dataset: proxies.json (Trojan, Hysteria2, WireGuard, TUIC, Shadowsocks, VLESS)
    dev_proxies_file = OUTPUTS_DEV_DIR / "proxies.json"
    if dev_proxies_file.exists():
        try:
            dev_data = json.loads(dev_proxies_file.read_text(encoding="utf-8"))
            trojans, hy2s, wgs, tuics, sss = [], [], [], [], []
            for item in dev_data.get("proxies", []):
                p = _parse_proxy_uri(item.get("uri", ""))
                if not p:
                    continue
                pr = p["protocol"]
                if pr == "trojan" and len(trojans) < 100:
                    trojans.append(p)
                elif pr in ("hysteria2", "hy2") and len(hy2s) < 100:
                    hy2s.append(p)
                elif pr in ("wireguard", "warp") and len(wgs) < 40:
                    wgs.append(p)
                elif pr == "tuic" and len(tuics) < 10:
                    tuics.append(p)
                elif pr in ("ss", "shadowsocks") and len(sss) < 50:
                    sss.append(p)
            raw_nodes.extend(trojans + hy2s + wgs + tuics + sss)
        except Exception:
            pass

    proxies = []
    for i, entry in enumerate(raw_nodes):
        idx = i + 1
        protocol = (entry.get("protocol") or "vless").lower()
        address = entry.get("address") or ""
        port = entry.get("port") or 443
        tag = entry.get("tag") or f"{protocol}-{idx}"
        params = entry.get("params") or {}
        raw = entry.get("raw") or ""

        security = params.get("security") or ("tls" if params.get("sni") or params.get("alpn") else "none")
        transport = params.get("type") or params.get("network") or "tcp"
        sni = params.get("sni") or ""
        host = params.get("host") or ""
        path = params.get("path") or ""
        pbk = params.get("pbk") or ""
        sid = params.get("sid") or ""
        flow = params.get("flow") or ""
        uuid_str = entry.get("user") or entry.get("password") or ""

        geo = resolve_geo_and_carrier(address, sni=sni, host=host)

        # Latency is measured later by probe_tcp_latency at publish time; here
        # it stays unmeasured instead of being invented from geography.

        security_grade = "A+" if security == "reality" else ("A" if security == "tls" else "B+")

        proxy_obj = {
            "id": f"px-{idx:04d}",
            "protocol": protocol,
            "name": f"{geo['country']}-{tag}",
            "server": address,
            "port": port,
            "uuid": uuid_str,
            "password": uuid_str,
            "security": security,
            "transport": transport,
            "sni": sni,
            "host": host,
            "path": path,
            "pbk": pbk,
            "sid": sid,
            "flow": flow,
            "country": geo["country"],
            "country_name": geo["country_name"],
            "flag": geo["flag"],
            "carrier": geo["carrier"],
            "org": geo["org"],
            "city": geo["city"],
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "geo_source": geo["geo_source"],
            "geo_verified": geo["geo_verified"],
            "latency": None,
            "latency_grade": None,
            "security_grade": security_grade,
            "raw_uri": raw
        }
        proxies.append(proxy_obj)

    return proxies


def compute_aggregate_stats(proxies: list[dict], catalog: dict) -> dict:
    """Compute aggregate dashboard statistics without inventing unavailable measurements."""
    dev_proxies_file = OUTPUTS_DEV_DIR / "proxies.json"
    cum_count = 0
    if dev_proxies_file.exists():
        try:
            cum_data = json.loads(dev_proxies_file.read_text(encoding="utf-8"))
            cum_count = cum_data.get("_count", cum_count)
        except Exception:
            pass

    active_sources = _configured_sources_count()

    proto_counts = {}
    sec_counts = {}
    trans_counts = {}
    country_counts = {}
    carrier_counts = {}
    latencies = []

    for p in proxies:
        proto = p["protocol"]
        proto_counts[proto] = proto_counts.get(proto, 0) + 1

        sec = p["security"]
        sec_counts[sec] = sec_counts.get(sec, 0) + 1

        tr = p["transport"]
        trans_counts[tr] = trans_counts.get(tr, 0) + 1

        c = p["country"]
        country_counts[c] = country_counts.get(c, 0) + 1

        car = p["carrier"]
        carrier_counts[car] = carrier_counts.get(car, 0) + 1

        if isinstance(p["latency"], (int, float)) and p["latency"] > 0:
            latencies.append(p["latency"])

    avg_lat = round(sum(latencies) / len(latencies)) if latencies else None
    min_lat = min(latencies) if latencies else None
    max_lat = max(latencies) if latencies else None
    # Health distribution is published alongside latency so the dashboard
    # can show how much of the fleet is verified-healthy, not just how
    # fast the healthy part answers.
    health_counts: dict[str, int] = {}
    reachable = 0
    for p in proxies:
        grade = p.get("health_grade")
        if isinstance(grade, str) and grade:
            health_counts[grade] = health_counts.get(grade, 0) + 1
        if p.get("probe_ok") is True:
            reachable += 1

    return {
        "generated_at": catalog.get("generated_at") or _generated_at(),
        "total_production_nodes": len(proxies),
        "total_cumulative_nodes": cum_count,
        "total_published_files": catalog["total_files"],
        "total_storage_bytes": catalog["total_size"],
        "total_storage_str": catalog["total_size_str"],
        "active_sources_count": active_sources,
        "protocols": proto_counts,
        "securities": sec_counts,
        "transports": trans_counts,
        "countries": country_counts,
        "carriers": carrier_counts,
        "avg_latency": avg_lat,
        "min_latency": min_lat,
        "max_latency": max_lat,
        "reachable_nodes": reachable,
        "health_distribution": health_counts,
        "pca_version": GOVERNED_PCA_VERSION,
        "pca_weights": GOVERNED_PCA_WEIGHTS,
    }


def _write_dashboard_data(catalog: dict, proxies: list[dict], stats: dict, data_js_file: Path) -> None:
    """Write the browser data module from one catalog/telemetry generation."""
    data_js_content = f"""/**
 * HUNTX Telemetry & Artifacts Data Store
 * Dynamically generated from outputs/ and outputs_dev/ pipeline outputs.
 * Timestamp: {stats["generated_at"]}
 */

// Compact separators: this module ships to the browser as a static asset and
// is never hand-edited, so the readable layout is pure download cost.
export const FALLBACK_CATALOG = {json.dumps(catalog, separators=(',', ':'))};

export const SAMPLE_PROXIES = {json.dumps(proxies, separators=(',', ':'))};

export const INGEST_STATS = {json.dumps(stats, separators=(',', ':'))};
"""
    data_js_file.parent.mkdir(parents=True, exist_ok=True)
    data_js_file.write_text(data_js_content, encoding="utf-8")


def generate_dashboard_data(
    outputs_dir: Path,
    outputs_dev_dir: Path,
    catalog_file: Path,
    data_js_file: Path,
) -> None:
    """Generate only data.js from an already verified catalog and current outputs.

    The Pages workflow owns the catalog and artifact copies. This entry point
    reuses that catalog and runs the telemetry stages against the same run's
    outputs, so the browser never has to merge generations.
    """
    global OUTPUTS_DIR, OUTPUTS_DEV_DIR, DATA_JS_FILE
    previous = (OUTPUTS_DIR, OUTPUTS_DEV_DIR, DATA_JS_FILE)
    try:
        OUTPUTS_DIR = Path(outputs_dir)
        OUTPUTS_DEV_DIR = Path(outputs_dev_dir)
        DATA_JS_FILE = Path(data_js_file)
        catalog = json.loads(Path(catalog_file).read_text(encoding="utf-8"))
        proxies = score_governed_pca(
            grade_proxy_health(
                probe_tcp_latency(
                    enrich_proxies_with_geoip(
                        drop_unreachable_proxies(parse_production_proxies())
                    )
                )
            )
        )
        stats = compute_aggregate_stats(proxies, catalog)
        _write_dashboard_data(catalog, proxies, stats, DATA_JS_FILE)
    finally:
        OUTPUTS_DIR, OUTPUTS_DEV_DIR, DATA_JS_FILE = previous


def generate_all() -> None:
    """Generate the static artifact catalog and frontend data module."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    catalog_entries: list[dict] = []
    seen_destinations: set[str] = set()

    sources = [
        ("release", OUTPUTS_DIR),
        ("dev", OUTPUTS_DEV_DIR),
    ]

    for section, source_dir in sources:
        if not source_dir.exists():
            continue
        dest_dir = ARTIFACTS_DIR / section
        dest_dir.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(source_dir.rglob("*")):
            if not src_file.is_file():
                continue

            rel_to_source = src_file.relative_to(source_dir)
            dst_file = dest_dir / rel_to_source
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_file, dst_file)

            destination_rel_docs = dst_file.relative_to(DOCS_DIR).as_posix()
            if destination_rel_docs in seen_destinations:
                continue
            seen_destinations.add(destination_rel_docs)

            file_size = src_file.stat().st_size
            digest = _sha256(src_file)
            ext, tags, desc = _infer_tags_and_type(src_file, section)

            if _is_frontend_product(section, src_file.name):
                entry = {
                    "filename": src_file.name,
                    "path": destination_rel_docs,
                    "section": section,
                    "size": file_size,
                    "size_str": _format_size(file_size),
                    "type": ext,
                    "ext": ext,
                    "tags": tags,
                    "description": desc,
                    "sha256": digest,
                    "hash": digest[:8],
                    "media_type": _infer_media_type(src_file),
                    "last_modified": datetime.fromtimestamp(
                        src_file.stat().st_mtime, timezone.utc
                    ).isoformat(),
                }
                catalog_entries.append(entry)

    total_size = sum(e["size"] for e in catalog_entries)
    catalog = {
        "schema_version": 1,
        "generated_at": _generated_at(),
        "total_files": len(catalog_entries),
        "total_size": total_size,
        "total_size_str": _format_size(total_size),
        "files": catalog_entries,
    }

    CATALOG_FILE.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "schema_version": 1,
        "artifact_count": len(catalog_entries),
        "artifacts": [
            {
                "path": e["path"].replace("artifacts/", "", 1),
                "size": e["size"],
                "sha256": e["sha256"],
                "media_type": e["media_type"],
            }
            for e in catalog_entries
        ],
    }
    (ARTIFACTS_DIR / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Parse production proxies from outputs, then enrich unresolved geography
    # with measured GeoIP before hubs and aggregate statistics are computed.
    # Parse production proxies, drop servers nothing on the internet can
    # resolve, enrich surviving geography with measured GeoIP, then probe.
    # Ordering matters: dropping unresolvable nodes first means GeoIP and
    # probes never spend their budget on nodes that cannot work at all.
    proxies = score_governed_pca(
        grade_proxy_health(
            probe_tcp_latency(
                enrich_proxies_with_geoip(
                    drop_unreachable_proxies(parse_production_proxies())
                )
            )
        )
    )
    stats = compute_aggregate_stats(proxies, catalog)

    # Generate docs/assets/js/data.js dynamically. The globe hubs the
    # dashboard renders are recomputed in the browser from whichever
    # dataset actually loaded (live artifact or bundled fallback), so a
    # second copy computed here would only go stale; the browser's own
    # clustering is the single source of truth.
    _write_dashboard_data(catalog, proxies, stats, DATA_JS_FILE)

    print(f"[site] Generated catalog with {len(catalog_entries)} files ({catalog['total_size_str']})")
    print(f"[site] Generated {len(proxies)} production proxies")
    print(f"[site] Written dynamic data store to {DATA_JS_FILE}")


def main() -> None:
    generate_all()


if __name__ == "__main__":
    main()
