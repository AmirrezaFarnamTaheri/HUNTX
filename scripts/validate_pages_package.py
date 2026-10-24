#!/usr/bin/env python3
"""Validate static resource dependencies in the exact Pages publication tree."""
from __future__ import annotations

import argparse
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
    return {"files_checked": scanned, "missing": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_pages_package(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
