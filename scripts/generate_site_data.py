import hashlib
import json
import mimetypes
import os
import shutil
import urllib.parse
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


def _infer_tags_and_type(path: Path, section: str) -> tuple[str, list[str], str]:
    """Derive dashboard type, tags, and description for a published artifact."""
    name = path.name.lower()
    tags = [section]
    ext = path.suffix.lstrip(".").upper() or "FILE"
    desc = ""

    if section == "release":
        tags.append("production")
        if "singbox" in name:
            ext = "SINGBOX"
            tags.extend(["singbox", "routing-profile", "outbounds"])
            desc = "Compiled Sing-box 1.10+ outbound routing profile with TLS/Reality rules"
        elif "v2ray" in name or "xray" in name:
            ext = "XRAY"
            tags.extend(["xray", "v2ray", "core-config"])
            desc = "Full Xray-core 1.8+ / V2Ray multi-protocol client configuration"
        elif "ovpn" in name:
            ext = "OVPN"
            tags.extend(["openvpn", "vpn", "gateway"])
            desc = "Standard OpenVPN multi-gateway client profile with TLS auth"
        elif "decoded.json" in name:
            ext = "JSON"
            tags.extend(["decoded", "parameters", "metadata"])
            desc = "Parsed and structured proxy connection parameters JSON dataset"
        elif "b64sub" in name:
            ext = "B64SUB"
            tags.extend(["subscription", "base64", "unified-feed"])
            desc = "Base64-encoded subscription feed for Shadowrocket, v2rayNG, and Streisand"
        elif "npvt" in name:
            ext = "NPVT"
            tags.extend(["subscription", "binary-feed"])
            desc = "Compact binary subscription feed for high-speed clients"
        elif "opaque_bundle" in name:
            ext = "BUNDLE"
            tags.extend(["bundle", "binary"])
            desc = "Cryptographically signed opaque proxy bundle"
        elif name.endswith(".md"):
            ext = "MD"
            tags.append("documentation")
            desc = "Production release documentation and checksum index"
    elif section == "dev":
        tags.append("cumulative")
        if name.startswith("proxies_chunk_"):
            ext = "CHUNK"
            tags.extend(["chunk", "split-feed", "lightweight"])
            desc = f"Lightweight split feed chunk ({path.name}) for bandwidth-constrained clients"
        elif "b64sub" in name:
            ext = "B64SUB"
            tags.extend(["subscription", "base64", "all-time"])
            desc = "All-time cumulative Base64 subscription feed across 49+ sources"
        elif name == "proxies.json":
            ext = "JSON"
            tags.extend(["aggregated", "all-time", "full-json"])
            desc = "Complete all-time cumulative proxy dataset with first-seen timestamps"
        elif name == "proxies.txt":
            ext = "TXT"
            tags.extend(["raw-uris", "deduped", "all-time"])
            desc = "All-time cumulative raw proxy URI list (SHA-256 deduplicated)"
        elif name == "_manifest.json":
            ext = "MANIFEST"
            tags.extend(["manifest", "telemetry", "state"])
            desc = "Durable cumulative first-seen timestamp manifest index"
        elif name.endswith(".md"):
            ext = "MD"
            tags.append("documentation")
            desc = "Development and cumulative output documentation"

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


def parse_production_proxies() -> list[dict]:
    """Load and normalize the production proxy snapshot for static publishing."""
    raw_nodes: list[dict] = []

    # 1. Curated production release dataset: all_sources.npvt.decoded.json
    decoded_file = OUTPUTS_DIR / "all_sources.npvt.decoded.json"
    if not decoded_file.exists():
        decoded_file = OUTPUTS_DIR / "all_sources_npvt_decoded.json"

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

        # No live probing exists in the static pipeline: latency stays
        # unmeasured instead of being invented from geography.

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


def cluster_globe_hubs(proxies: list[dict]) -> list[dict]:
    """Clusters all active production proxies into distinct 3D globe telemetry hubs."""
    hub_map: dict[str, dict] = {}

    for p in proxies:
        code = p["country"]
        if code == "ZZ" or not isinstance(p.get("latitude"), (int, float)) or not isinstance(p.get("longitude"), (int, float)):
            continue
        if code not in hub_map:
            lat, lon, city = GEO_COORDINATES.get(code, (p["latitude"], p["longitude"], f"{code} Hub"))
            hub_map[code] = {
                "name": city,
                "lat": lat,
                "lon": lon,
                "pings": [],
                "code": code,
                "country": p["country_name"],
                "carrier": p["carrier"],
                "count": 0
            }
        if isinstance(p["latency"], (int, float)) and p["latency"] > 0:
            hub_map[code]["pings"].append(p["latency"])
        hub_map[code]["count"] += 1

    hubs = []
    for code, h in hub_map.items():
        avg_ping = round(sum(h["pings"]) / len(h["pings"])) if h["pings"] else None
        hubs.append({
            "name": h["name"],
            "lat": h["lat"],
            "lon": h["lon"],
            "ping": avg_ping,
            "code": h["code"],
            "country": h["country"],
            "carrier": h["carrier"],
            "count": h["count"]
        })

    # Sort by node count descending
    hubs.sort(key=lambda x: x["count"], reverse=True)
    return hubs


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

    return {
        "generated_at": _generated_at(),
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
    }


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

    # Parse production proxies from outputs
    proxies = parse_production_proxies()
    hubs = cluster_globe_hubs(proxies)
    stats = compute_aggregate_stats(proxies, catalog)

    # Generate docs/assets/js/data.js dynamically
    data_js_content = f"""/**
 * HUNTX Telemetry & Artifacts Data Store
 * Dynamically generated from outputs/ and outputs_dev/ pipeline outputs.
 * Timestamp: {_generated_at()}
 */

export const FALLBACK_CATALOG = {json.dumps(catalog, indent=2)};

export const SAMPLE_PROXIES = {json.dumps(proxies, indent=2)};

export const GLOBE_HUBS = {json.dumps(hubs, indent=2)};

export const INGEST_STATS = {json.dumps(stats, indent=2)};
"""
    DATA_JS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_JS_FILE.write_text(data_js_content, encoding="utf-8")

    print(f"✅ Generated catalog with {len(catalog_entries)} files ({catalog['total_size_str']})")
    print(f"✅ Generated {len(proxies)} production proxies and {len(hubs)} telemetry hubs")
    print(f"✅ Written dynamic data store to {DATA_JS_FILE}")


def main() -> None:
    generate_all()


if __name__ == "__main__":
    main()
