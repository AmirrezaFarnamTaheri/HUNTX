"""Deterministic, network-free endpoint identity and optional IP-prefix evidence.

This module never resolves DNS, probes proxies, or infers IP location from
remarks, AS ownership, CDN marketing, or a hostname's top-level domain.
Its identity groups network endpoints, NOT independent proxy credentials.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
from pathlib import Path
from typing import Any, Mapping

from ..formats.common.singbox import parse_proxy_uri
from .remark_geoip import estimate_country, estimate_as_organization, is_anycast_address

_MAX_DATASET_BYTES = 8 * 1024 * 1024
_MAX_PREFIXES = 50_000
_MAX_DATASET_AGE = 31 * 86400
_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,79}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_UDP_PROTOCOLS = frozenset({"hysteria", "hysteria2", "tuic", "wireguard"})
_UNSAFE_DNS_SUFFIXES = (".local", ".localhost", ".internal", ".test", ".invalid")


def _positive_int(value: Any, *, upper: int = 2**32 - 1) -> int:
    if type(value) is not int or not 0 < value <= upper:
        raise ValueError("integer is outside the permitted range")
    return value


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate network intelligence field")
        record[key] = value
    return record


class PrefixIntelligence:
    """A size-bounded, expiring, user-supplied offline attribution snapshot.

    A prefix may assert an ASN/operator and an *estimated* country. An anycast
    prefix must NOT assign a geographic location: the serving POP depends on
    the observer and can change without the address changing.
    """

    def __init__(
        self,
        *,
        provider: str,
        observed_at: int,
        expires_at: int,
        entries: dict[tuple[int, int, int], dict[str, Any]],
        prefix_lengths: dict[int, set[int]],
    ) -> None:
        self.provider = provider
        self.observed_at = observed_at
        self.expires_at = expires_at
        self._entries = entries
        self._lengths = {
            version: sorted(lengths, reverse=True)
            for version, lengths in prefix_lengths.items()
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, Any], *, now: int | None = None
    ) -> "PrefixIntelligence":
        if not isinstance(document, Mapping):
            raise ValueError("network intelligence root must be an object")
        clock = int(time.time()) if now is None else int(now)
        if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
            raise ValueError("unsupported network intelligence schema")
        provider = document.get("provider")
        if not isinstance(provider, str) or not _PROVIDER.fullmatch(provider):
            raise ValueError("invalid network intelligence provider")
        observed_at = _positive_int(document.get("observed_at"), upper=2**62)
        expires_at = _positive_int(document.get("expires_at"), upper=2**62)
        if observed_at > clock or expires_at <= clock or expires_at <= observed_at:
            raise ValueError("network intelligence dataset is future-dated or expired")
        if expires_at - observed_at > _MAX_DATASET_AGE:
            raise ValueError("network intelligence validity exceeds 31 days")
        prefixes = document.get("prefixes")
        if not isinstance(prefixes, list) or len(prefixes) > _MAX_PREFIXES:
            raise ValueError("network intelligence prefix inventory is invalid or oversized")
        entries: dict[tuple[int, int, int], dict[str, Any]] = {}
        lengths: dict[int, set[int]] = {4: set(), 6: set()}
        for row in prefixes:
            if not isinstance(row, dict):
                raise ValueError("prefix entries must be objects")
            try:
                network = ipaddress.ip_network(row["cidr"], strict=True)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("malformed IP prefix") from exc
            if not network.is_global:
                raise ValueError("intelligence prefixes must be globally routable")
            if network.prefixlen < (8 if network.version == 4 else 16):
                raise ValueError("intelligence prefix is unreasonably broad")
            asn = row.get("asn")
            if asn is not None:
                asn = _positive_int(asn)
            country = row.get("country_code")
            if country is not None and (
                not isinstance(country, str)
                or not _COUNTRY.fullmatch(country)
                or country in {"XX", "ZZ"}
            ):
                raise ValueError("invalid country-code evidence")
            anycast = row.get("anycast", False)
            if type(anycast) is not bool:
                raise ValueError("anycast flag must be boolean")
            as_org = row.get("as_org")
            cdn = row.get("cdn_provider")
            for name, value in (("as_org", as_org), ("cdn_provider", cdn)):
                if value is not None and (
                    not isinstance(value, str) or not _PROVIDER.fullmatch(value)
                ):
                    raise ValueError(f"invalid {name}")
            # A CDN marker without independently attributed ASN evidence is
            # marketing, not a credible IP-prefix observation.
            if cdn is not None and asn is None:
                raise ValueError("CDN attribution requires ASN evidence")
            width = network.max_prefixlen
            key = (
                network.version, network.prefixlen,
                int(network.network_address) >> (width - network.prefixlen),
            )
            if key in entries:
                raise ValueError("duplicate network intelligence prefix")
            entries[key] = {
                "asn": asn, "as_org": as_org, "cdn_provider": cdn,
                "anycast": anycast, "country_code": country,
                "prefix": str(network),
            }
            lengths[network.version].add(network.prefixlen)
        return cls(
            provider=provider, observed_at=observed_at, expires_at=expires_at,
            entries=entries, prefix_lengths=lengths,
        )

    @classmethod
    def from_file(
        cls, path: Path | str, *, now: int | None = None
    ) -> "PrefixIntelligence":
        file = Path(path)
        if file.stat().st_size > _MAX_DATASET_BYTES:
            raise ValueError("network intelligence file exceeds 8 MiB")
        try:
            document = json.loads(file.read_text(encoding="utf-8"), object_pairs_hook=_pairs_unique)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid network intelligence JSON") from exc
        return cls.from_document(document, now=now)

    def lookup(self, address: ipaddress.IPv4Address | ipaddress.IPv6Address, *, now: int | None = None) -> dict[str, Any] | None:
        clock = int(time.time()) if now is None else int(now)
        if clock > self.expires_at or not address.is_global:
            return None
        bits = address.max_prefixlen
        value = int(address)
        for length in self._lengths[address.version]:
            match = self._entries.get(
                (address.version, length, value >> (bits - length))
            )
            if match is not None:
                return dict(match)
        return None


def _normalize_host(server: Any) -> tuple[str, str, ipaddress.IPv4Address | ipaddress.IPv6Address | None] | None:
    if not isinstance(server, str) or not server or len(server) > 253:
        return None
    host = server.strip().rstrip(".").lower()
    if not host:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Hostname validation is syntactic only; no network access occurs.
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        labels = host.split(".")
        if (
            len(labels) < 2 or len(host) > 253
            or host.endswith(_UNSAFE_DNS_SUFFIXES)
            or any(not label or len(label) > 63 or
                   not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                   for label in labels)
        ):
            return None
        return host, "dns_name", None
    return (
        str(address),
        "public_ip_literal" if address.is_global else "non_public_ip_literal",
        address,
    )


def describe_proxy_endpoint(
    uri: str,
    *,
    intelligence: PrefixIntelligence | None = None,
    intelligence_status: str = "not_configured",
) -> dict[str, Any] | None:
    """Describe public network endpoint evidence without exposing credentials.

    This does not make a network connection. URLs/remarks/passwords/UUIDs are
    deliberately absent. A DNS hostname is not silently assigned the region
    or ASN of a possible future resolution, including SNI or CDN fronts.
    """
    if not isinstance(uri, str) or not 0 < len(uri) <= 8192:
        return None
    try:
        node = parse_proxy_uri(uri)
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return None
    if node is None or type(node.port) is not int or not 1 <= node.port <= 65535:
        return None
    normalized = _normalize_host(node.server)
    if normalized is None:
        return None
    host, host_kind, address = normalized
    if not node.type or not isinstance(node.type, str):
        return None
    protocol = node.type.lower()
    endpoint_id = hashlib.sha256(
        f"network-endpoint-v1|{protocol}|{host}|{node.port}".encode("utf-8")
    ).hexdigest()[:24]
    udp_transport = (
        protocol in _UDP_PROTOCOLS or bool(node.naive_quic)
        or node.network == "udp" or node.transport_type == "quic"
    )
    status = (
        "unresolved_hostname" if address is None else
        "non_public_ip" if not address.is_global else
        "no_ip_prefix_evidence"
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "identity_scope": "network_endpoint_not_proxy_credential",
        "endpoint_id": endpoint_id,
        "protocol": protocol,
        "host": host,
        "port": node.port,
        "host_kind": host_kind,
        "ip": str(address) if address is not None and address.is_global else None,
        "ip_version": address.version if address is not None else None,
        "transport_kind": "udp" if udp_transport else "tcp",
        "transport": node.transport_type or node.network or None,
        "tls_mode": "reality" if node.tls_reality_enabled else "tls" if node.tls_enabled else "none",
        "asn": None,
        "as_org": None,
        "cdn_provider": None,
        "anycast": None,
        "geo": {"status": status, "country_code": None},
        "intelligence": {"status": intelligence_status},
        "dns_observation": (
            "not_applicable_literal" if address is not None else "not_measured"
        ),
        "tls_configuration": {
            "verification_disabled_in_link": bool(node.tls_insecure),
            "sni_present": bool(node.tls_server_name),
            "alpn_profile": (
                "unset" if not node.tls_alpn else
                "http2" if "h2" in node.tls_alpn else
                "http1" if "http/1.1" in node.tls_alpn else "other"
            ),
            "utls_fingerprint_present": bool(node.tls_utls_fingerprint),
            "reality_public_key_present": bool(node.tls_reality_public_key),
            "reality_short_id_present": bool(node.tls_reality_short_id),
        },
        "transport_configuration": {
            "path_present": bool(node.transport_path),
            "http_host_override_present": bool(node.transport_host),
            "grpc_service_present": bool(node.transport_service_name),
            "obfuscation_present": bool(node.obfs_type),
        },
        "diagnostic_findings": sorted(
            (["tls_verification_disabled"] if node.tls_insecure else [])
            + (["grpc_alpn_h2_not_declared"]
               if node.transport_type == "grpc" and node.tls_alpn
               and "h2" not in node.tls_alpn else [])
            + (["udp_requires_native_protocol_probe"]
               if udp_transport else [])
            + (["reality_requires_native_protocol_probe"]
               if node.tls_reality_enabled else [])
        ),
    }
    if intelligence is None and address is not None and address.is_global:
        # Publication already installs checksum-verified offline country data.
        # Reuse it in the independent endpoint inventory, where it was
        # previously missing and every public IP appeared geo-unknown.
        # An allocation estimate is not the location of a proxy's exit POP.
        ip_literal = str(address)
        if is_anycast_address(ip_literal):
            result["anycast"] = True
            result["geo"] = {
                "status": "anycast_location_unknown", "country_code": None,
            }
        else:
            country = estimate_country(ip_literal)
            if country is not None:
                result["geo"] = {
                    "status": "ip_allocation_country_estimate",
                    "country_code": country,
                }
                result["intelligence"] = {
                    "status": "offline_allocation_dataset",
                    "evidence": "checksum_verified_country_table",
                }
        org = estimate_as_organization(ip_literal)
        if org is not None:
            result["as_org"] = org
            # AS owner attribution does not imply a measured retail carrier.
            result["intelligence"] = {
                "status": "offline_allocation_dataset",
                "evidence": "checksum_verified_asn_table",
            }

    if intelligence is not None:
        result["intelligence"] = {
            "status": "no_match", "provider": intelligence.provider,
            "observed_at": intelligence.observed_at,
            "expires_at": intelligence.expires_at,
        }
        if address is not None and address.is_global:
            matched = intelligence.lookup(address)
            if matched is not None:
                result["asn"] = matched["asn"]
                result["as_org"] = matched["as_org"]
                result["cdn_provider"] = matched["cdn_provider"]
                result["anycast"] = matched["anycast"]
                result["geo"] = {
                    "status": (
                        "anycast_location_unknown" if matched["anycast"]
                        else "prefix_dataset_estimate" if matched["country_code"]
                        else "no_geolocation_evidence"
                    ),
                    "country_code": None if matched["anycast"] else matched["country_code"],
                }
                result["intelligence"]["status"] = "matched"
                result["intelligence"]["prefix"] = matched["prefix"]
    return result
