#!/usr/bin/env python3
"""Download checksum-verified public-domain IP attribution tables for publishing.

Source: sapics/ip-location-db, server-country and origin-asn PDDL datasets.
Country is a network allocation estimate, not a proxy's physical location;
origin-AS organization is a network owner, not necessarily a retail carrier.
No download is accepted unless it matches the upstream SHA-256 checksum.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

_BASE = "https://github.com/sapics/ip-location-db/releases/download"
_USER_AGENT = "HUNTX-geolocation-publisher/1.0"
_MAX_BYTES = 96 * 1024 * 1024
_ENTRIES = {
    "HUNTX_GEOIP_IPV4_CSV": "server-country-ipv4.csv",
    "HUNTX_GEOIP_IPV6_CSV": "server-country-ipv6.csv",
    "HUNTX_ASN_IPV4_CSV": "origin-asn-ipv4.csv",
    "HUNTX_ASN_IPV6_CSV": "origin-asn-ipv6.csv",
}


def _retrieve(url: str, limit: int = _MAX_BYTES) -> bytes:
    """Fetch a bounded HTTPS asset, retrying transient network failures."""
    if not url.startswith("https://"):
        raise ValueError("IP intelligence may only be downloaded using HTTPS")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = response.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("IP intelligence asset exceeds the configured size limit")
            return payload
        except (OSError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Unable to fetch IP intelligence asset: {url}") from last_error


def _valid_csv(payload: bytes, expected_columns: int) -> bool:
    """Refuse HTML error pages, empty files and unexpected dataset formats."""
    try:
        sample = payload[:8192].decode("utf-8")
        first = next(csv.reader(sample.splitlines()))
    except (UnicodeError, StopIteration, csv.Error):
        return False
    return len(first) == expected_columns and len(payload) >= 100


def prepare_tables(destination: Path, *, include_asn: bool = True) -> dict[str, Path]:
    """Fetch country/ASN CSVs and validate every upstream digest before use."""
    destination.mkdir(parents=True, exist_ok=True)
    selected = {
        key: filename for key, filename in _ENTRIES.items()
        if include_asn or key.startswith("HUNTX_GEOIP_")
    }
    results: dict[str, Path] = {}
    for key, filename in selected.items():
        checksums = _retrieve(f"{_BASE}/checksum/{filename}.sha256", limit=4096)
        matches = re.findall(rb"(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])", checksums.lower())
        if len(matches) != 1:
            raise ValueError(f"Upstream checksum is missing or ambiguous for {filename}")
        payload = _retrieve(f"{_BASE}/latest/{filename}")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != matches[0].decode("ascii"):
            raise ValueError(f"Upstream SHA-256 mismatch for {filename}")
        if not _valid_csv(payload, expected_columns=4 if "ASN_" in key else 3):
            raise ValueError(f"Invalid IP attribution CSV for {filename}")
        target = destination / filename
        temporary = destination / (filename + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
        results[key] = target.resolve()
        print(f"[geo] Verified {filename}: {len(payload)} bytes, sha256={digest[:12]}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--country-only", action="store_true")
    parser.add_argument("--github-env", type=Path, help="Append exported paths to GITHUB_ENV")
    args = parser.parse_args()

    tables = prepare_tables(args.output_dir, include_asn=not args.country_only)
    if args.github_env is not None:
        with args.github_env.open("a", encoding="utf-8") as env:
            for key, path in tables.items():
                env.write(f"{key}={path}\n")
    else:
        for key, path in tables.items():
            print(f"{key}={path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"::error title=IP attribution unavailable::{error}", file=sys.stderr)
        raise SystemExit(1) from error
