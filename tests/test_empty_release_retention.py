import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from huntx.core import output_ownership
from huntx.core.output_ownership import EMPTY_RELEASE_ARTIFACT, OUTPUT_OWNERSHIP_MANIFEST, export_owned_outputs
from huntx.pipeline.build import BuildPipeline


def runtime(tmp_path):
    return SimpleNamespace(
        paths=SimpleNamespace(output_dir=tmp_path / "outputs"),
        config=SimpleNamespace(routes=[]),
        _release_generated_at="2026-09-17T20:00:00Z",
        _release_window_start="2026-09-14T20:00:00Z",
        _output_retention_days=lambda: 365,
    )


def result(route="current", data=b"new"):
    return {"route_name": route, "format": "txt", "data": data}


def tree(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_success_removes_recent_owned_files_but_preserves_unowned(tmp_path):
    app = runtime(tmp_path)
    export_owned_outputs(app, [result("old")])
    root = app.paths.output_dir
    (root / "old_notes.txt").write_text("operator notes", encoding="utf-8")
    export_owned_outputs(app, [result()])
    assert not (root / "old.txt").exists()
    assert (root / "old_notes.txt").read_text(encoding="utf-8") == "operator notes"
    assert json.loads((root / OUTPUT_OWNERSHIP_MANIFEST).read_text(encoding="utf-8"))["files"] == {
        "current.txt": {"route": "current", "format": "txt"}
    }


def test_zero_record_success_exports_explicit_empty_then_recovers(tmp_path):
    app = runtime(tmp_path)
    export_owned_outputs(app, [result()])
    pipeline = BuildPipeline(Mock(), Mock(), Mock())
    results = pipeline.run({"name": "current", "formats": ["txt"]}, records=[])
    export_owned_outputs(app, results)
    root = app.paths.output_dir
    assert set(tree(root)) == {EMPTY_RELEASE_ARTIFACT, OUTPUT_OWNERSHIP_MANIFEST}
    assert json.loads((root / EMPTY_RELEASE_ARTIFACT).read_text(encoding="utf-8")) == {
        "schema_version": 1, "status": "success", "record_count": 0, "reason": "no_eligible_records",
        "generated_at": "2026-09-17T20:00:00+00:00", "min_ingested_at": "2026-09-14T20:00:00+00:00"
    }
    first = tree(root)
    export_owned_outputs(app, [])
    assert tree(root) == first
    export_owned_outputs(app, [result()])
    assert not (root / EMPTY_RELEASE_ARTIFACT).exists()
    assert (root / "current.txt").read_bytes() == b"new"


@pytest.mark.parametrize("bad", [[None], [{}], [result(data=b"")]])
def test_malformed_results_never_become_successful_empty(tmp_path, bad):
    app = runtime(tmp_path)
    export_owned_outputs(app, [result()])
    before = tree(app.paths.output_dir)
    with pytest.raises(ValueError):
        export_owned_outputs(app, bad)
    assert tree(app.paths.output_dir) == before


def test_nonempty_records_with_empty_builder_output_fail():
    registry = Mock()
    registry.get.return_value.build.return_value = b""
    pipeline = BuildPipeline(Mock(), Mock(), registry)
    with pytest.raises(RuntimeError, match="build failed"):
        pipeline.run({"name": "current", "formats": ["txt"]}, records=[{"record_type": "txt"}])


@pytest.mark.parametrize("failure", ["prepare", "replace", "prune", "manifest"])
def test_failed_export_restores_previous_snapshot(tmp_path, monkeypatch, failure):
    app = runtime(tmp_path)
    export_owned_outputs(app, [result("old"), result(data=b"previous")])
    root = app.paths.output_dir
    before = tree(root)
    write = output_ownership.atomic_write
    replace = output_ownership.os.replace
    unlink = Path.unlink

    def fail_write(path, data):
        if failure == "prepare" and Path(path).name == "current.txt":
            raise OSError("simulated prepare failure")
        return write(path, data)

    def fail_replace(src, dst):
        src = Path(src)
        if src.parent.name == "prepared" and (
            (failure == "replace" and src.name == "new.txt")
            or (failure == "manifest" and src.name == OUTPUT_OWNERSHIP_MANIFEST)
        ):
            raise OSError("simulated promotion failure")
        return replace(src, dst)

    def fail_unlink(path, *args, **kwargs):
        if failure == "prune" and path == root / "old.txt":
            raise OSError("simulated prune failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(output_ownership, "atomic_write", fail_write)
    monkeypatch.setattr(output_ownership.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError, match="simulated"):
        export_owned_outputs(app, [result(), result("new")])
    assert tree(root) == before


def test_empty_marker_never_overwrites_unowned_file(tmp_path):
    app = runtime(tmp_path)
    root = app.paths.output_dir
    root.mkdir()
    marker = root / EMPTY_RELEASE_ARTIFACT
    marker.write_text("operator notes", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unowned"):
        export_owned_outputs(app, [])
    assert marker.read_text(encoding="utf-8") == "operator notes"


@pytest.mark.parametrize("defer_output", [False, True])
def test_deferred_output_includes_derivatives_and_retains_direct_build_default(defer_output):
    registry = Mock()
    registry.get.return_value.build.return_value = b"vless://uuid@example.invalid:443"
    store = Mock()
    store.save_artifact.return_value = "f" * 64
    pipeline = BuildPipeline(Mock(), store, registry)
    route = {"name": "current", "formats": ["npvt"]}
    if defer_output:
        route["defer_output"] = True
    results = pipeline.run(route, records=[{"record_type": "npvt"}])
    assert len(results) > 1
    assert all(row["data"] for row in results)
    if defer_output:
        store.save_output.assert_not_called()
    else:
        assert store.save_output.call_count == len(results)
    store.save_artifact.assert_called_once()
