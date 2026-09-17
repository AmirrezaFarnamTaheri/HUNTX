import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from huntx.core import output_ownership as ownership
from huntx.pipeline.build import BuildPipeline


def _runtime(tmp_path):
    return SimpleNamespace(
        paths=SimpleNamespace(output_dir=tmp_path / "outputs"),
        config=SimpleNamespace(routes=[SimpleNamespace(name="route", formats=["txt"])]),
        _output_retention_days=lambda: 365,
        _release_generated_at="2026-09-17T00:00:00Z",
        _release_window_start="2026-09-14T00:00:00Z",
    )


def _result(data=b"current"):
    return {"route_name": "route", "format": "txt", "data": data}


def _tree(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_empty_snapshot_replaces_recent_owned_output_and_preserves_notes(tmp_path):
    runtime = _runtime(tmp_path)
    ownership.export_owned_outputs(runtime, [_result()])
    output = runtime.paths.output_dir
    (output / "notes.txt").write_text("operator notes", encoding="utf-8")
    ownership.export_owned_outputs(runtime, [])
    assert not (output / "route.txt").exists()
    marker = output / "empty-release.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "schema_version": 1, "status": "success", "record_count": 0,
        "reason": "no_eligible_records",
        "generated_at": "2026-09-17T00:00:00Z",
        "min_ingested_at": "2026-09-14T00:00:00Z",
    }
    assert (output / "notes.txt").read_text(encoding="utf-8") == "operator notes"
    ownership.export_owned_outputs(runtime, [_result(b"next")])
    assert not marker.exists()
    assert (output / "route.txt").read_bytes() == b"next"


def test_export_manifest_failure_restores_pruned_snapshot(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    ownership.export_owned_outputs(runtime, [_result()])
    before = _tree(runtime.paths.output_dir)
    replace = ownership.os.replace

    def fail_manifest(source, target):
        if (target == runtime.paths.output_dir / ownership.OUTPUT_OWNERSHIP_MANIFEST
                and source.parent.name == "prepared"):
            raise OSError("injected manifest promotion failure")
        return replace(source, target)

    monkeypatch.setattr(ownership.os, "replace", fail_manifest)
    with pytest.raises(OSError, match="injected"):
        ownership.export_owned_outputs(runtime, [])
    assert _tree(runtime.paths.output_dir) == before


@pytest.mark.parametrize("result", [None, {}, _result(b"")])
def test_malformed_result_is_not_successful_empty(tmp_path, result):
    runtime = _runtime(tmp_path)
    ownership.export_owned_outputs(runtime, [_result()])
    before = _tree(runtime.paths.output_dir)
    with pytest.raises(ValueError):
        ownership.export_owned_outputs(runtime, [result])
    assert _tree(runtime.paths.output_dir) == before


def test_nonempty_records_with_empty_builder_bytes_fail():
    repo, store, registry = Mock(), Mock(), Mock()
    registry.get.return_value.build.return_value = b""
    pipeline = BuildPipeline(repo, store, registry)
    with pytest.raises(RuntimeError, match="build failed"):
        pipeline.run({"name": "route", "formats": ["txt"]}, records=[{"record_type": "txt"}])
    store.save_artifact.assert_not_called()
    assert pipeline.run({"name": "route", "formats": ["txt"]}, records=[]) == []


def _release(tmp_path, changes=None):
    from huntx.store.release_manifest import build_release_manifest

    payload = {
        "schema_version": 1, "status": "success", "record_count": 0,
        "reason": "no_eligible_records", "generated_at": "2026-09-17T00:00:00Z",
        "min_ingested_at": "2026-09-14T00:00:00Z",
    }
    payload.update(changes or {})
    marker = tmp_path / ownership.EMPTY_RELEASE_ARTIFACT
    marker.write_text(json.dumps(payload), encoding="utf-8")
    return build_release_manifest(tmp_path, [marker])


def test_explicit_empty_validator_checks_integrity_and_marker(tmp_path):
    manifest = _release(tmp_path)
    assert ownership.is_explicit_empty_release(tmp_path, manifest)
    (tmp_path / ownership.EMPTY_RELEASE_ARTIFACT).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="size mismatch"):
        ownership.is_explicit_empty_release(tmp_path, manifest)


@pytest.mark.parametrize("changes", [
    {"record_count": False}, {"schema_version": True}, {"record_count": 1},
    {"status": "failed"}, {"unknown": 1}, {"generated_at": None},
    {"generated_at": "2026-09-17T00:00:00"},
    {"min_ingested_at": None}, {"min_ingested_at": ""},
    {"min_ingested_at": "2026-09-18T00:00:00Z"},
])
def test_explicit_empty_validator_rejects_invalid_semantics(tmp_path, changes):
    manifest = _release(tmp_path, changes)
    with pytest.raises(ValueError):
        ownership.is_explicit_empty_release(tmp_path, manifest)


def test_explicit_empty_validator_rejects_mixed_artifacts_and_missing_artifacts(tmp_path):
    from huntx.store.release_manifest import build_release_manifest

    _release(tmp_path)
    data = tmp_path / "data.txt"
    data.write_text("records", encoding="utf-8")
    mixed = build_release_manifest(tmp_path, [data, tmp_path / ownership.EMPTY_RELEASE_ARTIFACT])
    with pytest.raises(ValueError, match="accompany"):
        ownership.is_explicit_empty_release(tmp_path, mixed)
    ordinary = build_release_manifest(tmp_path, [data])
    assert not ownership.is_explicit_empty_release(tmp_path, ordinary)
    with pytest.raises(ValueError):
        ownership.is_explicit_empty_release(tmp_path, {"schema_version": 1, "artifact_count": 0, "artifacts": []})
