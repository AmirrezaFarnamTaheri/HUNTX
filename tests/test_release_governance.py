import json
from pathlib import Path

import pytest

from huntx.config.schema import SourceConfig, SourceTrustState
from huntx.store.release_manifest import (
    build_release_manifest,
    verify_release_manifest,
    write_manifest_atomic,
)


def test_discovered_source_requires_approval_evidence() -> None:
    with pytest.raises(ValueError):
        SourceConfig(
            id="candidate",
            type="v2ray_collector",
            trust_state=SourceTrustState.APPROVED,
            discovered_from="catalog-entry",
        )


def test_candidate_source_is_not_publication_eligible() -> None:
    source = SourceConfig(
        id="candidate",
        type="v2ray_collector",
        trust_state=SourceTrustState.CANDIDATE,
        discovered_from="catalog-entry",
    )
    assert source.publication_eligible is False


def test_approved_source_is_publication_eligible() -> None:
    source = SourceConfig(id="approved", type="v2ray_collector")
    assert source.publication_eligible is True


def test_manifest_hashes_and_verifies_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "feed.txt"
    artifact.write_text("artifact-content\n", encoding="utf-8")
    manifest = build_release_manifest(tmp_path, [artifact])
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["path"] == "feed.txt"
    manifest_path = tmp_path / "manifest.json"
    write_manifest_atomic(manifest_path, manifest)
    verify_release_manifest(
        tmp_path,
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )


def test_manifest_rejects_empty_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "empty.txt"
    artifact.write_bytes(b"")
    with pytest.raises(ValueError, match="Empty artifact"):
        build_release_manifest(tmp_path, [artifact])


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "feed.txt"
    artifact.write_text("original", encoding="utf-8")
    manifest = build_release_manifest(tmp_path, [artifact])
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        verify_release_manifest(tmp_path, manifest)


def test_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    artifact = tmp_path / "broken.json"
    artifact.write_text("not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        build_release_manifest(tmp_path, [artifact])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.update({"unexpected": True}),
        lambda manifest: manifest.update({"schema_version": 2}),
        lambda manifest: manifest["artifacts"][0].update({"extra": True}),
        lambda manifest: manifest["artifacts"][0].update({"sha256": "not-a-digest"}),
        lambda manifest: manifest["artifacts"][0].update({"size": True}),
        lambda manifest: manifest["artifacts"][0].update({"path": "../escape.txt"}),
    ],
)
def test_manifest_verifier_rejects_noncanonical_schema(tmp_path: Path, mutate) -> None:
    artifact = tmp_path / "feed.txt"
    artifact.write_text("artifact", encoding="utf-8")
    manifest = build_release_manifest(tmp_path, [artifact])
    mutate(manifest)

    with pytest.raises(ValueError):
        verify_release_manifest(tmp_path, manifest)


def test_manifest_rejects_symlink_before_resolution(tmp_path: Path) -> None:
    artifact = tmp_path / "feed.txt"
    artifact.write_text("artifact", encoding="utf-8")
    link = tmp_path / "alias.txt"
    try:
        link.symlink_to(artifact)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="Symlink"):
        build_release_manifest(tmp_path, [link])
