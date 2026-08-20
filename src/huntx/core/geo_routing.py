from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List
from urllib.parse import unquote, urlsplit

# Country inference is intentionally heuristic. Explicit display remarks win;
# otherwise only a hostname TLD is used. IP geolocation is not fabricated.
COUNTRY_TAG_REGEX = re.compile(r"\b([A-Z]{2})\b")

TLD_COUNTRY_MAP = {
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
COUNTRY_CODES = frozenset(TLD_COUNTRY_MAP.values())

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
}


def _hostname_from_uri(uri: str) -> str | None:
    if "://" not in uri:
        return None
    try:
        return urlsplit(uri).hostname
    except (TypeError, ValueError):
        return None


class GeoRoutingEngine:
    """Heuristic geo clustering and protocol taxonomy for proxy records."""

    @lru_cache(maxsize=4096)
    def infer_country_code(self, uri: str) -> str:
        """Infer a country tag from a remark or hostname TLD, else ``XX``."""
        if not isinstance(uri, str) or not uri:
            return "XX"

        if "#" in uri:
            remark = unquote(uri.split("#", 1)[1]).upper()
            for match in COUNTRY_TAG_REGEX.findall(remark):
                if match in COUNTRY_CODES:
                    return match

        host = _hostname_from_uri(uri)
        if host:
            normalized = host.rstrip(".").lower()
            for tld, code in TLD_COUNTRY_MAP.items():
                if normalized.endswith(tld):
                    return code

        return "XX"

    def normalize_protocol(self, protocol_str: Any) -> str:
        if not isinstance(protocol_str, str):
            return "unknown"
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
        """Enrich a proxy record without mutating the caller-owned mapping."""
        record = dict(proxy_record)
        raw_uri = record.get("raw_uri")
        if not isinstance(raw_uri, str):
            data = record.get("data")
            if isinstance(data, bytes):
                raw_uri = data.decode("utf-8", errors="ignore")
            elif isinstance(data, str):
                raw_uri = data
            else:
                raw_uri = ""

        proto_raw = record.get("protocol")
        if not isinstance(proto_raw, str) or not proto_raw.strip():
            proto_raw = raw_uri.split("://", 1)[0] if "://" in raw_uri else "unknown"

        country = self.infer_country_code(raw_uri)
        normalized_proto = self.normalize_protocol(proto_raw)

        record["raw_uri"] = raw_uri
        record["country_code"] = country
        record["protocol"] = normalized_proto
        record["taxonomy"] = {
            "is_fast": normalized_proto in {"hysteria2", "tuic", "vless"},
            "region_tier": 1 if country in {"US", "DE", "NL", "SG", "JP"} else 2,
        }
        return record

    def route_by_region(
        self,
        proxies: List[Dict[str, Any]],
        country_code: str,
    ) -> List[Dict[str, Any]]:
        """Filter proxies by an explicit or heuristically inferred country tag."""
        if not isinstance(country_code, str):
            return []
        target = country_code.strip().upper()
        if target not in COUNTRY_CODES:
            return []
        return [
            proxy
            for proxy in proxies
            if proxy.get("country_code") == target
            or self.infer_country_code(proxy.get("raw_uri", "")) == target
        ]

    def route_by_protocol(
        self,
        proxies: List[Dict[str, Any]],
        protocol: str,
    ) -> List[Dict[str, Any]]:
        """Filter proxies by normalized protocol taxonomy."""
        target_proto = self.normalize_protocol(protocol)
        if target_proto == "unknown":
            return []
        return [
            proxy
            for proxy in proxies
            if self.normalize_protocol(proxy.get("protocol")) == target_proto
        ]
