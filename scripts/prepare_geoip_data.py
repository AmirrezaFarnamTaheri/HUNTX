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
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

_BASE = "https://github.com/sapics/ip-location-db/releases/download"
_RELEASE_API = "https://api.github.com/repos/sapics/ip-location-db/releases/latest"
_METADATA_MAX_BYTES = 1024 * 1024
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


def _release_assets(selected: dict[str, str]) -> dict[str, tuple[str, str, int]]:
    """Tie the expected digest to each file in the SAME GitHub release.

    The upstream 'checksum' release is updated independently of 'latest'.
    Comparing those two releases incorrectly rejects valid CSVs whenever
    their scheduled publication times diverge. A GitHub-computed asset digest
    is authoritative for the corresponding asset in the 'latest' release.
    """
    raw = _retrieve(_RELEASE_API, limit=_METADATA_MAX_BYTES)
    try:
        metadata = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid upstream release metadata") from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("tag_name") != "latest"
        or not isinstance(metadata.get("assets"), list)
    ):
        raise ValueError("Invalid upstream latest release metadata")

    assets = metadata["assets"]
    verified: dict[str, tuple[str, str, int]] = {}
    for filename in selected.values():
        matches = [
            asset for asset in assets
            if isinstance(asset, dict) and asset.get("name") == filename
        ]
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous release asset for {filename}")
        asset = matches[0]
        url = f"{_BASE}/latest/{filename}"
        # Never let untrusted release JSON redirect data ingestion to another
        # host or to a different mutable asset. The digest is checked AGAIN
        # against actual downloaded bytes; no trust bypass is possible.
        if asset.get("browser_download_url") != url:
            raise ValueError(f"Invalid release asset URL for {filename}")
        digest = asset.get("digest")
        if not isinstance(digest, str) or re.fullmatch(
            r"sha256:[a-f0-9]{64}", digest,
        ) is None:
            raise ValueError(f"Missing or malformed release asset digest for {filename}")
        size = asset.get("size")
        if type(size) is not int or not 100 <= size <= _MAX_BYTES:
            raise ValueError(f"Invalid release asset size for {filename}")
        verified[filename] = (url, digest[7:], size)
    return verified


def prepare_tables(destination: Path, *, include_asn: bool = True) -> dict[str, Path]:
    """Stage complete, same-release SHA-256-verified country/ASN datasets."""
    destination.mkdir(parents=True, exist_ok=True)
    selected = {
        key: filename for key, filename in _ENTRIES.items()
        if include_asn or key.startswith("HUNTX_GEOIP_")
    }
    release_assets = _release_assets(selected)
    verified_bytes: dict[str, bytes] = {}
    # Verify ALL files before activating any. An upstream refresh during this
    # run must fail closed without corrupting the last validated local data.
    for key, filename in selected.items():
        url, expected_digest, expected_size = release_assets[filename]
        payload = _retrieve(url)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected_digest:
            raise ValueError(f"Upstream SHA-256 mismatch for {filename}")
        if len(payload) != expected_size:
            raise ValueError(f"Upstream asset size mismatch for {filename}")
        if not _valid_csv(payload, expected_columns=4 if "ASN_" in key else 3):
            raise ValueError(f"Invalid IP attribution CSV for {filename}")
        verified_bytes[filename] = payload
        print(f"[geo] Verified {filename}: {len(payload)} bytes, sha256={digest[:12]}")

    prepared: list[tuple[Path, Path]] = []
    results: dict[str, Path] = {}
    try:
        for filename, payload in verified_bytes.items():
            temporary = destination / (filename + ".tmp")
            temporary.write_bytes(payload)
            prepared.append((temporary, destination / filename))
        for temporary, target in prepared:
            os.replace(temporary, target)
        for key, filename in selected.items():
            results[key] = (destination / filename).resolve()
    finally:
        for temporary, _ in prepared:
            temporary.unlink(missing_ok=True)
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
