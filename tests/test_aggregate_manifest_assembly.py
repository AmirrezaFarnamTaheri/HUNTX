"""Aggregate Pages manifest must describe current verified artifacts, not old shell data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.assemble_generated_snapshot import rebuild_aggregate_artifact_manifest
from scripts.validate_pages_package import validate_pages_package


def test_assembler_regenerates_aggregate_index_from_final_catalog(tmp_path: Path):
    docs = tmp_path / "docs"
    release = docs / "artifacts" / "release"
    dev = docs / "artifacts" / "dev"
    release.mkdir(parents=True)
    dev.mkdir(parents=True)
    (docs / "index.html").write_text("<html></html>", encoding="utf-8")
    items = []
    for name, payload, directory in [
        ("all_sources.txt", b"synthetic-source", release),
        ("proxies.json", b'{"total":0}', dev),
    ]:
        target = directory / name
        target.write_bytes(payload)
        items.append({
            "path": "artifacts/" + directory.name + "/" + name,
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": "application/octet-stream",
        })
    (docs / "catalog.json").write_text(
        json.dumps({"files": items}), encoding="utf-8"
    )
    (docs / "artifacts" / "manifest.json").write_text(
        json.dumps({"artifact_count": 1, "artifacts": [
            {"path": "dev/removed.json", "size": 999, "sha256": "0" * 64}
        ]}), encoding="utf-8"
    )

    rebuild_aggregate_artifact_manifest(docs)

    result = json.loads(
        (docs / "artifacts" / "manifest.json").read_text(encoding="utf-8")
    )
    assert result["artifact_count"] == 2
    assert {entry["path"] for entry in result["artifacts"]} == {
        "dev/proxies.json", "release/all_sources.txt"
    }
    assert validate_pages_package(docs)["missing"] == []


def test_assembler_rejects_catalog_claiming_mismatched_hash(tmp_path: Path):
    docs = tmp_path / "docs"
    target = docs / "artifacts" / "release" / "feed.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"actual")
    (docs / "catalog.json").write_text(json.dumps({
        "files": [{
            "path": "artifacts/release/feed.txt",
            "size": len(b"actual"), "sha256": hashlib.sha256(b"bogus").hexdigest(),
        }]
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        rebuild_aggregate_artifact_manifest(docs)
