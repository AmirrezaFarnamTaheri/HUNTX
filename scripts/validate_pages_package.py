#!/usr/bin/env python3
"""Validate static resource dependencies in the exact Pages publication tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

_JS_IMPORT_RE = re.compile(
    r'\b(?:from\s+|import\s*(?:\(\s*)?)["\'](\.[^"\']+)["\']'
)
_JS_NEW_URL_RE = re.compile(r'\bnew\s+URL\(["\'](\.[^"\']+)["\']\s*,\s*import\.meta\.url')
_CSS_URL_RE = re.compile(r'\burl\(\s*["\']?([^"\'\)]+)')
_CSS_IMPORT_RE = re.compile(r'@import\s+["\']([^"\']+)["\']')


class _HTMLAssets(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        ref = None
        if tag in {"script", "img", "iframe", "source", "video", "audio"}:
            ref = attributes.get("src")
        elif tag == "link" and any(
            part in str(attributes.get("rel") or "").lower().split()
            for part in {"stylesheet", "manifest", "icon", "modulepreload", "preload"}
        ):
            ref = attributes.get("href")
        elif tag == "a":
            candidate = attributes.get("href") or ""
            if urlsplit(candidate).path.endswith(".html"):
                ref = candidate
        if ref:
            self.references.append(ref)


def _references(path: Path) -> list[str]:
    if path.suffix.lower() == ".html":
        parser = _HTMLAssets()
        parser.feed(path.read_text(encoding="utf-8"))
        return parser.references
    if path.suffix.lower() == ".js":
        source = path.read_text(encoding="utf-8")
        return (
            _JS_IMPORT_RE.findall(source)
            + _JS_NEW_URL_RE.findall(source)
        )
    if path.suffix.lower() == ".css":
        source = path.read_text(encoding="utf-8")
        return _CSS_URL_RE.findall(source) + _CSS_IMPORT_RE.findall(source)
    return []


_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _verify_artifact(root: Path, relative: str, item: dict, *, manifest: str) -> None:
    """Check integrity of each declared downloadable artifact in the Pages tree."""
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise ValueError(f"unsafe {manifest} artifact path")
    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or "\\\\" in relative
        or "?" in relative
        or "#" in relative
    ):
        raise ValueError(f"unsafe {manifest} artifact path")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{manifest} artifact escapes package root") from exc
    if not candidate.is_file():
        raise ValueError(f"Missing {manifest} artifact {relative}")
    expected_size = item.get("size")
    digest = item.get("sha256")
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError(f"Invalid size in {manifest} artifact {relative}")
    if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
        raise ValueError(f"Invalid sha256 in {manifest} artifact {relative}")
    if candidate.stat().st_size != expected_size:
        raise ValueError(f"{manifest} artifact size mismatch {relative}")
    hasher = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    if hasher.hexdigest() != digest:
        raise ValueError(f"{manifest} artifact digest mismatch {relative}")


def _verify_publication_artifacts(root: Path) -> int:
    """Validate exact catalog and release manifest bytes before Pages upload."""
    checked = 0
    catalog_paths: set[str] | None = None
    catalog = root / "catalog.json"
    if catalog.is_file():
        try:
            document = json.loads(catalog.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid Pages catalog.json") from exc
        if not isinstance(document, dict) or not isinstance(document.get("files"), list):
            raise ValueError("Invalid Pages catalog file list")
        seen: set[str] = set()
        catalog_paths = seen
        for entry in document["files"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("Invalid Pages catalog artifact")
            relative = entry["path"]
            if not relative.startswith("artifacts/"):
                raise ValueError(f"unsafe catalog artifact path {relative}")
            if relative in seen:
                raise ValueError(f"Duplicate catalog artifact {relative}")
            seen.add(relative)
            _verify_artifact(root, relative, entry, manifest="catalog")
            checked += 1
    release = root / "artifacts" / "release" / "manifest.json"
    if release.is_file():
        try:
            document = json.loads(release.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid release manifest") from exc
        if not isinstance(document, dict) or not isinstance(document.get("artifacts"), list):
            raise ValueError("Invalid release manifest artifact list")
        if "artifact_count" in document and document["artifact_count"] != len(document["artifacts"]):
            raise ValueError("Release manifest artifact count mismatch")
        seen: set[str] = set()
        for entry in document["artifacts"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("Invalid release manifest artifact")
            rel = entry["path"]
            if not rel or rel.startswith("/") or ".." in Path(rel).parts:
                raise ValueError("unsafe release artifact path")
            if rel in seen:
                raise ValueError(f"Duplicate release artifact {rel}")
            seen.add(rel)
            _verify_artifact(root, "artifacts/release/" + rel, entry, manifest="release")
            checked += 1

    # A legacy aggregate manifest can survive a shell overlay even after the
    # release-specific manifest and catalog are replaced. Validate this public
    # index too; valid checksums elsewhere must not conceal stale downloads.
    aggregate = root / "artifacts" / "manifest.json"
    if aggregate.is_file():
        try:
            document = json.loads(aggregate.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid aggregate artifact manifest") from exc
        if not isinstance(document, dict) or not isinstance(document.get("artifacts"), list):
            raise ValueError("Invalid aggregate manifest artifact list")
        entries = document["artifacts"]
        if document.get("artifact_count") != len(entries):
            raise ValueError("Aggregate manifest artifact count mismatch")
        aggregate_paths: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("Invalid aggregate manifest artifact")
            relative = entry["path"]
            if not relative or relative.startswith("/") or ".." in Path(relative).parts:
                raise ValueError("unsafe aggregate manifest artifact path")
            path = "artifacts/" + relative
            if path in aggregate_paths:
                raise ValueError(f"Duplicate aggregate artifact {relative}")
            aggregate_paths.add(path)
            _verify_artifact(root, path, entry, manifest="aggregate")
            checked += 1
        if catalog_paths is not None and aggregate_paths != catalog_paths:
            raise ValueError("aggregate manifest/catalog file inventory mismatch")
    return checked


def _verify_authenticated_feed_conservation(root: Path) -> None:
    """Fail closed if an authenticated identity is lost in the final Pages tree.

    A count or SHA-256 file checksum alone cannot expose a substituted proxy.
    Match each exact canonical connection digest in the primary and alternate
    feeds against both the authenticated HTTPS sidecar and the admission ledger.
    Retain every admitted connection regardless of latency, quality or country;
    unverified candidates remain in the ledger, not the working subscription.

    Authentication expiry is evaluated by the health consumer; historical
    evidence must stay readable after expiry, not become a fresh health claim.
    """
    import math
    import sys
    from collections import Counter

    release = root / "artifacts" / "release"
    for stem in ("all_sources", "all_sources_sub"):
        feed = release / f"{stem}.txt"
        health_path = release / f"{stem}_health.json"
        gate_path = release / f"{stem}_gate.json"
        if not health_path.exists() and not gate_path.exists():
            # Older published bundles and explicit empty releases may lack an
            # authenticated feed. Do not invent verification on their behalf.
            continue
        if not all(path.is_file() for path in (feed, health_path, gate_path)):
            raise ValueError(f"{stem}: incomplete authenticated feed evidence")

        # This validator is also run as a direct script by GitHub Actions,
        # without a package-install step for the HUNTX source tree itself.
        source_dir = str(Path(__file__).resolve().parents[1] / "src")
        if source_dir not in sys.path:
            sys.path.insert(0, source_dir)
        from huntx.formats.npvt import canonical_proxy_identity

        lines = [line.strip() for line in feed.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        digests = [
            hashlib.sha256(canonical_proxy_identity(line).encode("utf-8")).hexdigest()
            for line in lines
        ]
        identities = set(digests)
        if len(identities) != len(digests):
            raise ValueError(f"{stem}: duplicate semantic proxy identities in final feed")

        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"{stem}: invalid authenticated evidence JSON") from exc
        records = health.get("records") if isinstance(health, dict) else None
        if (not isinstance(records, dict)
                or health.get("schema_version") != 1
                or health.get("evidence") != "publisher_authenticated_https"
                or type(health.get("admitted_count")) is not int
                or health["admitted_count"] != len(records)):
            raise ValueError(f"{stem}: invalid authenticated sidecar")
        if set(records) != identities:
            raise ValueError(
                f"{stem}: authenticated sidecar identity mismatch "
                f"(feed={len(identities)} sidecar={len(records)})"
            )
        for measurement in records.values():
            if not isinstance(measurement, dict):
                raise ValueError(f"{stem}: invalid authenticated measurement")
            values = [measurement.get(key) for key in
                      ("checked_at", "expires_at", "duration_ms")]
            if (any(type(value) not in (int, float) or not math.isfinite(value)
                    for value in values)
                    or values[1] < values[0] or not 0 <= values[2] <= 30000):
                raise ValueError(f"{stem}: invalid authenticated measurement")

        ledger = gate.get("identities") if isinstance(gate, dict) else None
        reasons = gate.get("reasons") if isinstance(gate, dict) else None
        if (not isinstance(ledger, dict) or not isinstance(reasons, dict)
                or gate.get("schema_version") != 1
                or gate.get("scope") != "single_authenticated_https_sweep"
                or any(type(gate.get(key)) is not int or gate[key] < 0
                       for key in ("candidates", "admitted", "rejected"))
                or gate["candidates"] != len(ledger)
                or gate["admitted"] + gate["rejected"] != gate["candidates"]
                or any(not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None
                       or not isinstance(status, str) or not status
                       for key, status in ledger.items())
                or any(not isinstance(reason, str)
                       or type(count) is not int or count < 0
                       for reason, count in reasons.items())
                or sum(reasons.values()) != gate["candidates"]
                or Counter(ledger.values()) != Counter(reasons)):
            raise ValueError(f"{stem}: invalid authenticated admission gate")
        admitted = {key for key, status in ledger.items() if status == "admitted"}
        if gate["admitted"] != len(admitted) or admitted != identities:
            raise ValueError(
                f"{stem}: admitted identity mismatch between gate and feed "
                f"(gate={len(admitted)} feed={len(identities)})"
            )


def _verify_dashboard_feed_parity(root: Path) -> None:
    """Require every immutable primary URI to appear in the deployed dashboard.

    The checked-in historical snapshot omitted every VMess entry even though
    the client feed carried them. UI-only resource checks could not detect it.
    Do not print URI values: raw links include proxy credentials.
    """
    feed = root / "artifacts" / "release" / "all_sources.txt"
    module = root / "assets" / "js" / "data.js"
    if not feed.is_file() or not module.is_file():
        return
    lines = [line.strip() for line in feed.read_text(encoding="utf-8").splitlines() if line.strip()]
    body = module.read_text(encoding="utf-8")
    declaration = "export const SAMPLE_PROXIES = "
    if body.count(declaration) != 1:
        raise ValueError("Pages dashboard SAMPLE_PROXIES export is missing or duplicated")
    try:
        records, _ = json.JSONDecoder().raw_decode(body.split(declaration, 1)[1])
    except json.JSONDecodeError as exc:
        raise ValueError("Pages dashboard SAMPLE_PROXIES JSON invalid") from exc
    if not isinstance(records, list) or any(
        not isinstance(node, dict) or not isinstance(node.get("raw_uri"), str)
        for node in records
    ):
        raise ValueError("Pages dashboard SAMPLE_PROXIES must contain raw_uri strings")
    rendered = [node["raw_uri"] for node in records]
    if (
        len(lines) != len(rendered)
        or len(set(lines)) != len(lines)
        or len(set(rendered)) != len(rendered)
        or set(lines) != set(rendered)
    ):
        raise ValueError(
            "Pages dashboard and release feed identities differ "
            f"(feed={len(lines)} dashboard={len(rendered)}); refusing stale publication"
        )


def validate_pages_package(root: Path) -> dict[str, object]:
    """Fail closed on missing local files and paths that escape the static root.

    HTTP URLs, data URLs, mailto links and fragment-only navigation are
    intentionally external to this check.
    """
    root = root.resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        raise ValueError("Pages package has no index.html")
    missing: set[str] = set()
    scanned = 0
    for source in sorted(root.rglob("*")):
        if source.suffix.lower() not in {".html", ".js", ".css"} or not source.is_file():
            continue
        scanned += 1
        for target in _references(source):
            parsed = urlsplit(target.strip())
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            if target.startswith(("data:", "#", "//")):
                continue
            decoded = unquote(parsed.path)
            if decoded.startswith("/"):
                candidate = root / decoded.lstrip("/")
            else:
                candidate = source.parent / decoded
            resolved = candidate.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError("Pages reference escapes package root") from exc
            if not resolved.is_file():
                missing.add(relative.as_posix())
    if missing:
        raise ValueError("Missing Pages assets: " + ", ".join(sorted(missing)[:25]))
    _verify_publication_artifacts(root)
    _verify_authenticated_feed_conservation(root)
    _verify_dashboard_feed_parity(root)
    return {"files_checked": scanned, "missing": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_pages_package(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
