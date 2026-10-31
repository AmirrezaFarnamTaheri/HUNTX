"""Validate asset references in the exact assembled Pages directory."""
from pathlib import Path
import hashlib
import json

import pytest

from scripts.validate_pages_package import validate_pages_package


def test_pages_asset_validator_follows_html_and_js_imports(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<script type="module" src="./assets/js/app.js"></script>'
        '<link rel="stylesheet" href="assets/css/app.css">'
        '<a href="network-doctor.html">Doctor</a>', encoding="utf-8"
    )
    (tmp_path / "network-doctor.html").write_text("<html></html>", encoding="utf-8")
    js = tmp_path / "assets" / "js"
    css = tmp_path / "assets" / "css"
    js.mkdir(parents=True)
    css.mkdir(parents=True)
    (js / "app.js").write_text('import "./widget.js";', encoding="utf-8")
    (js / "widget.js").write_text('export const ready = true;', encoding="utf-8")
    (css / "app.css").write_text('body{background:url("../icons/bg.svg")}', encoding="utf-8")
    (tmp_path / "assets" / "icons").mkdir()
    (tmp_path / "assets" / "icons" / "bg.svg").write_text("<svg></svg>", encoding="utf-8")

    result = validate_pages_package(tmp_path)
    assert result["missing"] == []
    assert result["files_checked"] >= 3
    (js / "widget.js").unlink()
    with pytest.raises(ValueError, match="assets/js/widget.js"):
        validate_pages_package(tmp_path)


def test_pages_contract_rejects_missing_manifest_and_escape(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<link rel="manifest" href="manifest.json">'
        '<script src="../../escape.js"></script>', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="manifest.json|escapes"):
        validate_pages_package(tmp_path)


def test_pages_catalog_requires_exact_artifacts_and_hashes(tmp_path: Path):
    """A working UI shell is not sufficient if its downloads are missing."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    release = tmp_path / "artifacts" / "release"
    release.mkdir(parents=True)
    payload = b'{"nodes":[]}'
    artifact = release / "feed.json"
    artifact.write_bytes(payload)
    catalog = {
        "files": [{
            "path": "artifacts/release/feed.json",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }]
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    assert validate_pages_package(tmp_path)["missing"] == []
    artifact.write_bytes(b'{"nodes":[1]}')
    with pytest.raises(ValueError, match="feed.json"):
        validate_pages_package(tmp_path)
    artifact.unlink()
    with pytest.raises(ValueError, match="feed.json"):
        validate_pages_package(tmp_path)


def test_pages_release_manifest_requires_exact_artifact_bytes(tmp_path: Path):
    """All output formats listed by the release manifest need verified bytes."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    release = tmp_path / "artifacts" / "release"
    release.mkdir(parents=True)
    artifact = release / "nodes.txt"
    artifact.write_bytes(b"synthetic-socks-link")
    manifest = {
        "artifacts": [{
            "path": "nodes.txt", "size": artifact.stat().st_size,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }]
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_pages_package(tmp_path)["missing"] == []
    artifact.write_bytes(b"changed")
    with pytest.raises(ValueError, match="nodes.txt"):
        validate_pages_package(tmp_path)


def test_pages_catalog_rejects_files_escaping_upload_root(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "catalog.json").write_text(
        json.dumps({"files": [{"path": "../private.txt", "size": 1, "sha256": "0" * 64}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes|unsafe"):
        validate_pages_package(tmp_path)
