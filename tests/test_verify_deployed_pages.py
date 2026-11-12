"""Verify deployed Pages bytes, not only successful deploy-pages actions."""

import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest

from scripts import verify_deployed_pages as pages


HISTORY = (
    "artifacts/dev/proxies.json",
    "artifacts/dev/proxies.txt",
    "artifacts/dev/proxies_b64sub.txt",
    "artifacts/manifest.json",
    "artifacts/quality/proxy-churn.json",
)


def _snapshot(root: Path) -> dict[str, bytes]:
    binary = {
        "index.html": b"<!doctype html><title>HUNTX</title>",
        "assets/js/data.js": b"export const generated = true;\n",
        "artifacts/release/all_sources.txt": b"vless://unit.example\n",
        "artifacts/dev/proxies.json": b'{"nodes": []}\n',
        "artifacts/dev/proxies.txt": b"historical://connection\n",
        "artifacts/dev/proxies_b64sub.txt": b"aGlzdG9yaWNhbDovL2Nvbm5lY3Rpb24=\n",
        "artifacts/quality/proxy-churn.json": b'{"appeared": []}\n',
    }
    for relative, body in binary.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

    def entry(relative):
        body = binary[relative]
        return {
            "path": relative,
            "size": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }

    catalog = {
        "schema_version": 1,
        "generated_at": "2026-11-12T13:30:00Z",
        "files": [entry("artifacts/release/all_sources.txt")],
        "total_files": 1,
    }
    release = {
        "schema_version": 1,
        "artifact_count": 1,
        "artifacts": [{
            **entry("artifacts/release/all_sources.txt"),
            "path": "all_sources.txt",
        }],
    }
    aggregate = {
        "schema_version": 1,
        "artifact_count": 1,
        "artifacts": [{
            **entry("artifacts/release/all_sources.txt"),
            "path": "release/all_sources.txt",
        }],
    }
    binary["catalog.json"] = (json.dumps(catalog, sort_keys=True) + "\n").encode()
    binary["artifacts/release/manifest.json"] = (
        json.dumps(release, sort_keys=True) + "\n"
    ).encode()
    binary["artifacts/manifest.json"] = (
        json.dumps(aggregate, sort_keys=True) + "\n"
    ).encode()
    for relative in ("catalog.json", "artifacts/release/manifest.json", "artifacts/manifest.json"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(binary[relative])
    return binary


class Reply(io.BytesIO):
    status = 200


def _site(monkeypatch, stored, overrides=None):
    requests = []
    overrides = overrides or {}

    def open_url(request, timeout):
        del timeout
        url = request.full_url
        path = urlsplit(url).path.removeprefix("/HUNTX/")
        requests.append(path)
        replacement = overrides.get(path)
        if isinstance(replacement, Exception):
            raise replacement
        if callable(replacement):
            replacement = replacement()
        if replacement is None:
            replacement = stored[path]
        return Reply(replacement)

    monkeypatch.setattr(pages, "urlopen", open_url)
    return requests


def test_matches_every_declared_release_and_all_historical_paths(tmp_path, monkeypatch):
    stored = _snapshot(tmp_path)
    requested = _site(monkeypatch, stored)
    report = pages.verify_live_publication(
        tmp_path, "https://owner.github.io/HUNTX/",
        attempts=2, interval=0, request_timeout=1, max_seconds=10,
    )
    assert report["verified_files"] == len(stored)
    assert "artifacts/release/all_sources.txt" in requested
    assert set(HISTORY).issubset(requested)
    assert "assets/js/data.js" in requested


def test_retries_stale_catalog_until_exact_snapshot_is_served(tmp_path, monkeypatch):
    stored = _snapshot(tmp_path)
    state = {"n": 0}

    def occasionally_stale():
        state["n"] += 1
        return b'{"generated_at":"2026-10-24"}' if state["n"] == 1 else stored["catalog.json"]

    _site(monkeypatch, stored, {"catalog.json": occasionally_stale})
    report = pages.verify_live_publication(
        tmp_path, "https://owner.github.io/HUNTX/",
        attempts=3, interval=0, request_timeout=1, max_seconds=10,
    )
    assert state["n"] >= 2
    assert report["verified_files"] == len(stored)


def test_missing_public_historical_file_is_never_declared_published(tmp_path, monkeypatch):
    stored = _snapshot(tmp_path)
    path = HISTORY[0]
    err = HTTPError("https://owner.github.io/HUNTX/" + path, 404, "Not Found", None, None)
    _site(monkeypatch, stored, {path: err})
    with pytest.raises(pages.LivePagesError, match="artifacts/dev/proxies.json"):
        pages.verify_live_publication(
            tmp_path, "https://owner.github.io/HUNTX/",
            attempts=2, interval=0, request_timeout=1, max_seconds=10,
        )


def test_corrupted_public_release_blob_is_never_accepted(tmp_path, monkeypatch):
    stored = _snapshot(tmp_path)
    path = "artifacts/release/all_sources.txt"
    _site(monkeypatch, stored, {path: b"tampered"})
    with pytest.raises(pages.LivePagesError, match="all_sources.txt"):
        pages.verify_live_publication(
            tmp_path, "https://owner.github.io/HUNTX/",
            attempts=2, interval=0, request_timeout=1, max_seconds=10,
        )


def test_local_snapshot_requires_all_five_cumulative_paths(tmp_path):
    _snapshot(tmp_path)
    (tmp_path / HISTORY[0]).unlink()
    with pytest.raises(pages.LivePagesError, match="artifacts/dev/proxies.json"):
        pages.expected_public_paths(tmp_path)


def test_rejects_non_https_deployment_url(tmp_path):
    _snapshot(tmp_path)
    with pytest.raises(pages.LivePagesError, match="HTTPS"):
        pages.verify_live_publication(
            tmp_path, "http://owner.github.io/HUNTX/",
            attempts=1, interval=0, request_timeout=1, max_seconds=10,
        )
