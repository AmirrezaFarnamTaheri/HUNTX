"""Offline, bounded country lookup for publish-time proxy remarks.

CSV columns: inclusive IP start, inclusive IP end, ISO alpha-2 country.
IP allocation geography is an estimate, not the location of an anycast POP.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import csv
import ipaddress
import os
from pathlib import Path

# Known globally anycast services should never get a physical country flag
# from an allocation-country table.
_ANYCAST = tuple(ipaddress.ip_network(net) for net in (
    "1.1.1.0/24", "1.0.0.0/24", "8.8.8.0/24", "8.8.4.0/24",
    "9.9.9.0/24", "149.112.112.0/24", "104.16.0.0/12",
    "172.64.0.0/13", "162.158.0.0/15", "188.114.96.0/20",
    "2606:4700::/32", "2001:4860:4860::/48",
))


def _public_address(host: str):
    try:
        ip = ipaddress.ip_address(host)
    except (TypeError, ValueError):
        return None
    return ip if ip.is_global else None


def _anycast(address) -> bool:
    return any(address in prefix for prefix in _ANYCAST if address.version == prefix.version)


@lru_cache(maxsize=4)
def _load_ranges(filename: str):
    path = Path(filename)
    if not path.is_file() or path.stat().st_size > 35 * 1024 * 1024:
        return (), (), ()
    rows = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.reader(stream):
            if len(row) != 3:
                continue
            try:
                start = ipaddress.ip_address(row[0])
                end = ipaddress.ip_address(row[1])
            except ValueError:
                continue
            code = row[2].strip().upper()
            if start.version != end.version or int(start) > int(end):
                continue
            if len(code) != 2 or not code.isascii() or not code.isalpha() or code in {"ZZ", "XX"}:
                continue
            rows.append((int(start), int(end), code))
    rows.sort()
    return tuple(row[0] for row in rows), tuple(row[1] for row in rows), tuple(row[2] for row in rows)


def estimate_country(host: str) -> str | None:
    """Country for a public IP with offline evidence, else unknown.

    Does not DNS-resolve or make network requests. Anycast remains unknown.
    """
    ip = _public_address(host)
    if ip is None or _anycast(ip):
        return None
    key = "HUNTX_GEOIP_IPV4_CSV" if ip.version == 4 else "HUNTX_GEOIP_IPV6_CSV"
    filename = os.environ.get(key, "").strip()
    if not filename:
        return None
    try:
        starts, ends, countries = _load_ranges(filename)
    except (OSError, UnicodeError, csv.Error):
        return None
    index = bisect_right(starts, int(ip)) - 1
    if index < 0 or int(ip) > ends[index]:
        return None
    return countries[index]


@lru_cache(maxsize=4)
def _load_asn_ranges(filename: str):
    """Read the PDDL origin-AS range table once for each configured file."""
    path = Path(filename)
    if not path.is_file() or path.stat().st_size > 96 * 1024 * 1024:
        return (), (), ()
    rows = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.reader(stream):
            if len(row) != 4:
                continue
            try:
                start = ipaddress.ip_address(row[0])
                end = ipaddress.ip_address(row[1])
                number = int(row[2])
            except (TypeError, ValueError):
                continue
            organization = row[3].strip()
            if (start.version != end.version or int(start) > int(end)
                    or number <= 0 or not organization or len(organization) > 160):
                continue
            rows.append((int(start), int(end), organization))
    rows.sort()
    return tuple(row[0] for row in rows), tuple(row[1] for row in rows), tuple(row[2] for row in rows)


def estimate_as_organization(host: str) -> str | None:
    """Estimate the network's origin-AS operator from a public IP.

    The returned AS organization is not necessarily a consumer mobile carrier
    or an accurate physical server location. No DNS or network I/O occurs.
    """
    ip = _public_address(host)
    if ip is None:
        return None
    key = "HUNTX_ASN_IPV4_CSV" if ip.version == 4 else "HUNTX_ASN_IPV6_CSV"
    filename = os.environ.get(key, "").strip()
    if not filename:
        return None
    try:
        starts, ends, organizations = _load_asn_ranges(filename)
    except (OSError, UnicodeError, csv.Error):
        return None
    index = bisect_right(starts, int(ip)) - 1
    if index < 0 or int(ip) > ends[index]:
        return None
    return organizations[index]
