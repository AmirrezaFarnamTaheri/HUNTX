import re
<<<<<<< Updated upstream
from typing import Dict, Any, List, Optional
from functools import lru_cache


=======
from typing import Dict, Any, List
from functools import lru_cache

>>>>>>> Stashed changes
# Standard ISO 3166-1 alpha-2 country codes regex pattern in remark tags
COUNTRY_TAG_REGEX = re.compile(r"\b([A-Z]{2})\b")
IP_HOST_REGEX = re.compile(r"@?([a-zA-Z0-9\.\-]+):(\d+)")

# Known TLD to Country mappings
TLD_COUNTRY_MAP = {
<<<<<<< Updated upstream
    ".de": "DE", ".fr": "FR", ".uk": "GB", ".us": "US", ".jp": "JP",
    ".nl": "NL", ".sg": "SG", ".ca": "CA", ".au": "AU", ".ir": "IR",
    ".kr": "KR", ".cn": "CN", ".ru": "RU", ".hk": "HK", ".tw": "TW",
    ".se": "SE", ".fi": "FI", ".ch": "CH", ".it": "IT", ".es": "ES"
}

SUPPORTED_PROTOCOLS = {
    "vless", "vmess", "trojan", "shadowsocks", "ss",
    "hysteria2", "hy2", "tuic", "wireguard", "wg", "anytls"
=======
    ".de": "DE",
    ".fr": "FR",
    ".uk": "GB",
    ".us": "US",
    ".jp": "JP",
    ".nl": "NL",
    ".sg": "SG",
    ".ca": "CA",
    ".au": "AU",
    ".ir": "IR",
    ".kr": "KR",
    ".cn": "CN",
    ".ru": "RU",
    ".hk": "HK",
    ".tw": "TW",
    ".se": "SE",
    ".fi": "FI",
    ".ch": "CH",
    ".it": "IT",
    ".es": "ES",
}

SUPPORTED_PROTOCOLS = {
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "ss",
    "hysteria2",
    "hy2",
    "tuic",
    "wireguard",
    "wg",
    "anytls",
>>>>>>> Stashed changes
}


class GeoRoutingEngine:
    """
    Intelligent geo-clustering, protocol taxonomy, and dynamic target routing engine.
    """

    @lru_cache(maxsize=1024)
    def infer_country_code(self, uri: str) -> str:
        """
        Infers the 2-letter ISO country code from proxy remark tags or hostname TLDs.
        Returns 'XX' if country code cannot be determined.
        """
        # 1. Search for explicit hashtag remarks e.g. #US - Node 1
        if "#" in uri:
            remark = uri.split("#", 1)[1]
            matches = COUNTRY_TAG_REGEX.findall(remark)
            for m in matches:
<<<<<<< Updated upstream
                if m in {"US", "DE", "FR", "GB", "NL", "SG", "JP", "CA", "AU", "IR", "KR", "CN", "RU", "HK", "TW", "SE", "FI", "CH", "IT", "ES"}:
=======
                if m in {
                    "US",
                    "DE",
                    "FR",
                    "GB",
                    "NL",
                    "SG",
                    "JP",
                    "CA",
                    "AU",
                    "IR",
                    "KR",
                    "CN",
                    "RU",
                    "HK",
                    "TW",
                    "SE",
                    "FI",
                    "CH",
                    "IT",
                    "ES",
                }:
>>>>>>> Stashed changes
                    return m

        # 2. Check TLD from host address
        match = IP_HOST_REGEX.search(uri)
        if match:
            host = match.group(1).lower()
            for tld, code in TLD_COUNTRY_MAP.items():
                if host.endswith(tld):
                    return code

        return "XX"

    def normalize_protocol(self, protocol_str: str) -> str:
        proto = protocol_str.lower().strip()
        if proto in ("ss", "shadowsocks"):
            return "shadowsocks"
        if proto in ("hy2", "hysteria2"):
            return "hysteria2"
        if proto in ("wg", "wireguard"):
            return "wireguard"
        if proto in SUPPORTED_PROTOCOLS:
            return proto
        return "unknown"

    def classify_proxy(self, proxy_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches a proxy record with country_code, normalized protocol, and taxonomy metadata.
        """
        record = dict(proxy_record)
<<<<<<< Updated upstream
        raw_uri = record.get("raw_uri") or (record.get("data").decode("utf-8") if isinstance(record.get("data"), bytes) else "")
=======
        data = record.get("data")
        raw_uri = record.get("raw_uri") or (data.decode("utf-8") if isinstance(data, bytes) else "")
>>>>>>> Stashed changes
        proto_raw = record.get("protocol") or (raw_uri.split("://", 1)[0] if "://" in raw_uri else "unknown")

        country = self.infer_country_code(raw_uri)
        normalized_proto = self.normalize_protocol(proto_raw)

        record["country_code"] = country
        record["protocol"] = normalized_proto
        record["taxonomy"] = {
            "is_fast": normalized_proto in {"hysteria2", "tuic", "vless"},
            "region_tier": 1 if country in {"US", "DE", "NL", "SG", "JP"} else 2,
        }

        return record

    def route_by_region(self, proxies: List[Dict[str, Any]], country_code: str) -> List[Dict[str, Any]]:
        """
        Filters proxies for a specific ISO country code.
        """
        target = country_code.upper()
<<<<<<< Updated upstream
        return [p for p in proxies if p.get("country_code") == target or self.infer_country_code(p.get("raw_uri", "")) == target]
=======
        return [
            p
            for p in proxies
            if p.get("country_code") == target or self.infer_country_code(p.get("raw_uri", "")) == target
        ]
>>>>>>> Stashed changes

    def route_by_protocol(self, proxies: List[Dict[str, Any]], protocol: str) -> List[Dict[str, Any]]:
        """
        Filters proxies matching a target protocol taxonomy.
        """
        target_proto = self.normalize_protocol(protocol)
        return [p for p in proxies if p.get("protocol") == target_proto]
