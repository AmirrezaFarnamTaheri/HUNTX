"""The published base64 subscription URL must survive output standardization."""
import json
from types import SimpleNamespace

from huntx.core.output_ownership import OUTPUT_OWNERSHIP_MANIFEST, export_owned_outputs

ALIAS = "all_sources.npvt.b64sub"
CANONICAL = "all_sources_npvt_b64sub.txt"


def _export(out_root, results):
    config = SimpleNamespace(routes=[SimpleNamespace(name="all_sources", formats=["npvt"])])
    orchestrator = SimpleNamespace(
        paths=SimpleNamespace(output_dir=out_root),
        config=config,
        _output_retention_days=lambda: 0,
    )
    export_owned_outputs(orchestrator, results)
    return orchestrator.paths.output_dir


def test_b64sub_alias_is_emitted_byte_identical(tmp_path):
    out = _export(tmp_path / "outputs", [{"route_name": "all_sources", "format": "npvt.b64sub", "data": b"c3Vic2NyaWJl"}])
    assert (out / ALIAS).read_bytes() == (out / CANONICAL).read_bytes() == b"c3Vic2NyaWJl"
    manifest = json.loads((out / OUTPUT_OWNERSHIP_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["files"][ALIAS] == {"route": "all_sources", "format": "npvt.b64sub"}


def test_previously_owned_file_absent_from_next_snapshot_is_pruned(tmp_path):
    out = _export(tmp_path / "outputs", [{"route_name": "all_sources", "format": "npvt", "data": b"vmess://a\n"}])
    legacy = out / "all_sources.npvt.nekobox.json"
    legacy.write_bytes(b"{}")
    manifest = json.loads((out / OUTPUT_OWNERSHIP_MANIFEST).read_text(encoding="utf-8"))
    manifest["files"]["all_sources.npvt.nekobox.json"] = {"route": "all_sources", "format": "npvt.nekobox.json"}
    (out / OUTPUT_OWNERSHIP_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")

    _export(out, [{"route_name": "all_sources", "format": "npvt", "data": b"vmess://a\n"}])

    assert not legacy.exists()


def test_unowned_legacy_derivative_is_pruned_when_replaced(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    legacy = out / "all_sources.npvt.nekobox.json"
    legacy.write_text('{"outbounds": [{"type": "vless"}]}', encoding="utf-8")
    canonical = b'[{"type": "vless", "tag": "node"}]'

    _export(out, [{"route_name": "all_sources", "format": "npvt.nekobox.json", "data": canonical}])

    assert not legacy.exists()
    assert (out / "all_sources_npvt_nekobox.json").read_bytes() == canonical


def test_unowned_unrelated_file_is_never_pruned(tmp_path):
    out = _export(tmp_path / "outputs", [{"route_name": "all_sources", "format": "npvt", "data": b"x"}])
    (out / "operator_notes.txt").write_text("keep", encoding="utf-8")
    _export(out, [{"route_name": "all_sources", "format": "npvt", "data": b"y"}])
    assert (out / "operator_notes.txt").read_text(encoding="utf-8") == "keep"


def test_b64sub_alias_tracks_successive_snapshots(tmp_path):
    out = tmp_path / "outputs"
    for data in (b"Zmlyc3Q=", b"c2Vjb25k"):
        _export(out, [{"route_name": "all_sources", "format": "npvt.b64sub", "data": data}])
        assert (out / ALIAS).read_bytes() == (out / CANONICAL).read_bytes() == data
        manifest = json.loads((out / OUTPUT_OWNERSHIP_MANIFEST).read_text(encoding="utf-8"))
        assert manifest["files"][ALIAS] == manifest["files"][CANONICAL]
