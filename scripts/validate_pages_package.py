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
    catalog = root / "catalog.json"
    if catalog.is_file():
        try:
            document = json.loads(catalog.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid Pages catalog.json") from exc
        if not isinstance(document, dict) or not isinstance(document.get("files"), list):
            raise ValueError("Invalid Pages catalog file list")
        seen: set[str] = set()
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
    return checked


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
