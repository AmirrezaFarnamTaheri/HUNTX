#!/usr/bin/env python3
"""Fail closed unless GitHub Pages serves the exact verified publication bytes.

Actions/deploy-pages succeeding does not prove that the public CDN has
propagated the new release, nor that cumulative download URLs are present.
This verifier runs after deployment, before advancing generated-outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen
from typing import Any


class LivePagesError(ValueError):
    """The public site cannot be attested to the published snapshot."""


# These five paths disappeared when a native Pages writer overwrote the
# cumulative publication. Verify all five even if a catalog omits them.
_HISTORICAL_PATHS = (
    "artifacts/dev/proxies.json",
    "artifacts/dev/proxies.txt",
    "artifacts/dev/proxies_b64sub.txt",
    "artifacts/manifest.json",
    "artifacts/quality/proxy-churn.json",
)
_BOOTSTRAP = ("catalog.json", "artifacts/release/manifest.json")
_CORE = ("index.html", "assets/js/data.js", *_BOOTSTRAP, *_HISTORICAL_PATHS)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _relative(raw: Any) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or raw.startswith("/")
        or "\\" in raw
        or "?" in raw
        or "#" in raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        raise LivePagesError("Unsafe artifact path in public manifest")
    return raw


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LivePagesError(f"Missing or invalid {path.name}") from exc
    if not isinstance(data, dict):
        raise LivePagesError(f"Invalid {path.name} object")
    return data


def _file_digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(block)
            hasher.update(block)
    return hasher.hexdigest(), total


def expected_public_paths(root: Path) -> dict[str, tuple[str, int]]:
    """Verify all local manifest/catalog items and mandatory cumulative files."""
    root = root.resolve()
    catalog = _read_object(root / "catalog.json")
    release = _read_object(root / "artifacts/release/manifest.json")
    aggregate = _read_object(root / "artifacts/manifest.json")
    catalog_rows = catalog.get("files")
    release_rows = release.get("artifacts")
    aggregate_rows = aggregate.get("artifacts")
    if not all(isinstance(rows, list) for rows in (
        catalog_rows, release_rows, aggregate_rows
    )):
        raise LivePagesError("Pages catalog or artifact manifest lacks entries")
    if (
        catalog.get("total_files") != len(catalog_rows)
        or release.get("artifact_count") != len(release_rows)
        or aggregate.get("artifact_count") != len(aggregate_rows)
    ):
        raise LivePagesError("Pages catalog or manifest artifact count mismatch")

    listed: dict[str, tuple[str, int]] = {}

    def add_entry(relative: str, item: dict[str, Any]) -> None:
        relative = _relative(relative)
        digest = item.get("sha256")
        size = item.get("size")
        if (
            type(size) is not int or size < 0
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
        ):
            raise LivePagesError(f"Invalid checksum/size for {relative}")
        entry = (digest, size)
        if relative in listed and listed[relative] != entry:
            raise LivePagesError(f"Conflicting manifest checksums for {relative}")
        listed[relative] = entry

    for item in catalog_rows:
        if not isinstance(item, dict):
            raise LivePagesError("Invalid catalog file entry")
        add_entry(item.get("path"), item)
    for item in release_rows:
        if not isinstance(item, dict):
            raise LivePagesError("Invalid release file entry")
        add_entry("artifacts/release/" + _relative(item.get("path")), item)
    for item in aggregate_rows:
        if not isinstance(item, dict):
            raise LivePagesError("Invalid aggregate file entry")
        add_entry("artifacts/" + _relative(item.get("path")), item)

    expected: dict[str, tuple[str, int]] = {}
    for relative in sorted(set(_CORE) | set(listed)):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise LivePagesError("Pages artifact escapes snapshot root") from exc
        if not path.is_file():
            raise LivePagesError(f"Required Pages artifact missing: {relative}")
        digest, size = _file_digest(path)
        if relative in listed and (digest, size) != listed[relative]:
            raise LivePagesError(f"Local artifact integrity mismatch: {relative}")
        expected[relative] = (digest, size)
    return expected


def _url_root(page_url: str) -> str:
    url = urlsplit(page_url)
    if (
        url.scheme != "https" or not url.netloc
        or url.username or url.password or url.query or url.fragment
    ):
        raise LivePagesError("Pages deployment URL must be a clean HTTPS URL")
    return page_url.rstrip("/") + "/"


def _remote_digest(url: str, *, timeout: float, deadline: float) -> tuple[str, int]:
    if time.monotonic() >= deadline:
        raise LivePagesError("Live Pages verification time budget exhausted")
    request = Request(
        url,
        headers={
            "User-Agent": "HUNTX-Live-Pages-Integrity/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept-Encoding": "identity",
        },
    )
    hasher = hashlib.sha256()
    count = 0
    with urlopen(request, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise LivePagesError("Live Pages returned non-200 status")
        while True:
            if time.monotonic() >= deadline:
                raise LivePagesError("Live Pages verification time budget exhausted")
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), count


def verify_live_publication(
    root: Path,
    page_url: str,
    *,
    attempts: int = 12,
    interval: float = 10.0,
    request_timeout: float = 20.0,
    max_seconds: float = 600.0,
) -> dict[str, Any]:
    """Validate live bytes for each catalog, release and historical artifact."""
    base = _url_root(page_url)
    if attempts <= 0 or interval < 0 or request_timeout <= 0 or max_seconds <= 0:
        raise LivePagesError("Invalid bounded live-verification options")
    expected = expected_public_paths(root)
    deadline = time.monotonic() + max_seconds

    def check(relative: str) -> None:
        target = urljoin(base, quote(relative, safe="/"))
        digest, size = _remote_digest(
            target,
            timeout=min(request_timeout, max(0.01, deadline - time.monotonic())),
            deadline=deadline,
        )
        if (digest, size) != expected[relative]:
            raise LivePagesError(f"Stale or corrupt public file: {relative}")

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            for relative in _BOOTSTRAP:
                check(relative)
            break
        except (LivePagesError, OSError) as exc:
            last_error = exc
            if attempt + 1 == attempts or time.monotonic() >= deadline:
                raise LivePagesError(
                    f"Live Pages catalog or release manifest did not propagate: {exc}"
                ) from exc
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    else:
        raise LivePagesError(f"Live Pages bootstrap check failed: {last_error}")

    # A matching catalog proves the new version reached the CDN. Verify the
    # actual downloaded bytes, including every release-manifest derivative and
    # the historically missing cumulative URLs, rather than trusting link text.
    for relative in expected:
        if relative in _BOOTSTRAP:
            continue
        for attempt in range(3):
            try:
                check(relative)
                break
            except (LivePagesError, OSError) as exc:
                if attempt == 2 or time.monotonic() >= deadline:
                    raise LivePagesError(
                        f"Live Pages download verification failed: {relative} ({exc})"
                    ) from exc
                time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))

    return {
        "verified_files": len(expected),
        "catalog_sha256": expected["catalog.json"][0],
        "release_manifest_sha256": expected["artifacts/release/manifest.json"][0],
        "historical_downloads_verified": len(_HISTORICAL_PATHS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--max-seconds", type=float, default=600.0)
    args = parser.parse_args()
    report = verify_live_publication(
        args.snapshot_root,
        args.page_url,
        attempts=args.attempts,
        interval=args.interval,
        request_timeout=args.request_timeout,
        max_seconds=args.max_seconds,
    )
    print("Live Pages integrity verified: " + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
