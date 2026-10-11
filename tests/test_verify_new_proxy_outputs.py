from __future__ import annotations

import pytest

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_verify_output() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_output.py"
    spec = importlib.util.spec_from_file_location("verify_output", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_output_treats_new_client_json_as_json(tmp_path):
    verifier = _load_verify_output()
    xray = tmp_path / "all_sources_npvt_xray.json"
    xray.write_text(json.dumps({"outbounds": [{"protocol": "vless"}]}), encoding="utf-8")
    nekobox = tmp_path / "all_sources_npvt_nekobox.json"
    nekobox.write_text(
        json.dumps([{"type": "vless", "tag": "node"}]),
        encoding="utf-8",
    )

    assert verifier.validate_file(xray)["type"] == "json"
    assert verifier.validate_file(nekobox)["type"] == "json"


def test_verify_output_treats_raw_derivative_as_proxy_text(tmp_path):
    verifier = _load_verify_output()
    raw = tmp_path / "all_sources_npvt_raw.txt"
    raw.write_text(
        "vless://11111111-2222-3333-4444-555555555555@example.com:443?encryption=none#Node\n",
        encoding="utf-8",
    )

    stats = verifier.validate_file(raw)
    assert stats["type"] == "text"
    assert stats["protocols"]["vless"] == 1


OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"


def _committed_outputs(pattern: str) -> list[Path]:
    """Committed source-of-truth artifacts the dashboard is generated from."""
    return sorted(OUTPUTS_DIR.glob(pattern))


def test_committed_nekobox_outputs_are_node_feeds_not_client_configs():
    """NekoBox imports a top-level JSON array as individually selectable nodes."""
    files = _committed_outputs("*nekobox.json")
    assert files, "the NekoBox node feed must be published"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        # A configuration-shaped {"outbounds": [...]} object makes the client
        # import the whole artifact as one custom profile instead of a list.
        assert isinstance(payload, list), f"{path.name} is a {type(payload).__name__}, not a node array"
        assert payload, f"{path.name} publishes no nodes"
        for node in payload:
            assert node.get("type"), f"{path.name} has an outbound without a type"
            assert node.get("tag"), f"{path.name} has an outbound without a tag"


def test_committed_client_configs_are_complete_importable_profiles():
    """Sing-box and Xray JSON are profile imports: a client needs inbounds and outbounds."""
    files = _committed_outputs("*singbox.json") + _committed_outputs("*xray.json")
    assert files, "at least one client configuration must be published"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), f"{path.name} is not a configuration object"
        assert payload.get("inbounds"), f"{path.name} has no inbounds; it is not a runnable profile"
        assert payload.get("outbounds"), f"{path.name} has no outbounds to import"


def test_committed_base64_feeds_decode_to_proxy_uris():
    """A v2rayN/v2rayNG subscription is base64 over newline-separated URIs."""
    from huntx.formats.common.b64 import b64_decode

    files = _committed_outputs("*b64sub*")
    assert files, "the base64 subscription feed must be published"
    for path in files:
        encoded = path.read_text(encoding="utf-8").strip()
        assert encoded, f"{path.name} is empty"
        decoded = b64_decode(encoded)
        lines = [line for line in decoded.splitlines() if line.strip()]
        assert lines, f"{path.name} decodes to no URIs"
        for line in lines:
            assert "://" in line, f"{path.name} has a non-URI line: {line[:40]}"


def test_malformed_derived_products_are_marked_invalid(tmp_path):
    verifier = _load_verify_output()
    broken_json = tmp_path / "all_sources_singbox_profile.json"
    broken_json.write_text("{", encoding="utf-8")
    broken_yaml = tmp_path / "all_sources_clash.yaml"
    broken_yaml.write_text("proxies:\\n  - not-json", encoding="utf-8")
    assert verifier.validate_file(broken_json).get("invalid") is True
    assert verifier.validate_file(broken_yaml).get("invalid") is True


def test_full_profiles_are_not_classified_as_decoded_dataset(tmp_path):
    verifier = _load_verify_output()
    path = tmp_path / "all_sources_xray_profile.json"
    path.write_text(json.dumps({"inbounds": [], "outbounds": []}), encoding="utf-8")
    assert verifier.validate_file(path)["type"] == "json"


def test_node_and_profile_json_contracts_are_not_interchangeable(tmp_path):
    verifier = _load_verify_output()
    cases = (
        ("all_sources_singbox_nodes.json", {"inbounds": [{}], "outbounds": [{"type": "trojan", "tag": "a"}]}, True),
        ("all_sources_singbox.json", {"outbounds": [{"type": "trojan", "tag": "a"}]}, True),
        ("all_sources_xray_nodes.json", {"outbounds": [{"protocol": "vless", "tag": "a"}], "route": {}}, True),
        ("all_sources_xray.json", {"outbounds": [{"protocol": "vless", "tag": "a"}]}, True),
        ("all_sources_singbox_nodes.json", {"outbounds": [{"type": "trojan", "tag": "a"}]}, False),
        ("all_sources_xray_nodes.json", {"outbounds": [{"protocol": "vless", "tag": "a"}]}, False),
        ("all_sources_singbox.json", {
            "inbounds": [{"type": "mixed"}], "dns": {}, "route": {},
            "outbounds": [{"type": "trojan", "tag": "a"}]}, False),
        ("all_sources_xray.json", {
            "inbounds": [{"protocol": "socks"}], "outbounds": [{"protocol": "vmess", "tag": "a"}]}, False),
    )
    for number, (filename, payload, should_fail) in enumerate(cases):
        target = tmp_path / str(number)
        target.mkdir()
        file = target / filename
        file.write_text(json.dumps(payload), encoding="utf-8")
        result = verifier.validate_file(file)
        assert bool(result.get("invalid")) is should_fail, (filename, result)


def test_legacy_nekobox_array_keeps_import_compatibility(tmp_path):
    verifier = _load_verify_output()
    file = tmp_path / "all_sources_nekobox.json"
    file.write_text(json.dumps([{"type": "trojan", "tag": "node"}]), encoding="utf-8")
    assert not verifier.validate_file(file).get("invalid")


def test_invalid_artifact_cannot_erase_last_good_dist(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    outputs.mkdir()
    dist.mkdir()
    (dist / "last-good.txt").write_text("retained", encoding="utf-8")
    (outputs / "all_sources_singbox_nodes.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)
    with pytest.raises(RuntimeError, match="refusing to publish malformed"):
        verifier.main()
    assert (dist / "last-good.txt").read_text(encoding="utf-8") == "retained"


def test_copy_error_preserves_existing_dist(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    outputs.mkdir()
    dist.mkdir()
    (outputs / "all_sources.txt").write_text("vless://id@example.test:443#node\n", encoding="utf-8")
    (dist / "previous.txt").write_text("safe", encoding="utf-8")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)

    def fail_copy(*_args, **_kwargs):
        raise OSError("simulated disk exhaustion")

    monkeypatch.setattr(verifier.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="simulated disk exhaustion"):
        verifier.main()
    assert (dist / "previous.txt").read_text(encoding="utf-8") == "safe"


def test_install_rename_error_rolls_back_previous_dist(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    outputs.mkdir()
    dist.mkdir()
    (outputs / "all_sources.txt").write_text("vless://id@example.test:443#node\n", encoding="utf-8")
    (dist / "previous.txt").write_text("safe", encoding="utf-8")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)
    real_replace = verifier.os.replace

    def rename(src, dst):
        if Path(src).name == "prepared" and Path(dst) == dist:
            raise OSError("simulated directory installation failure")
        return real_replace(src, dst)

    monkeypatch.setattr(verifier.os, "replace", rename)
    with pytest.raises(OSError, match="simulated directory installation failure"):
        verifier.main()
    assert (dist / "previous.txt").read_text(encoding="utf-8") == "safe"


def test_successful_install_removes_old_dist_files(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    outputs.mkdir()
    dist.mkdir()
    (dist / "obsolete.txt").write_text("old", encoding="utf-8")
    payload = "vless://id@example.test:443#node\n"
    (outputs / "all_sources.txt").write_text(payload, encoding="utf-8")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)
    verifier.main()
    assert not (dist / "obsolete.txt").exists()
    assert (dist / "all_sources.txt").read_text(encoding="utf-8") == payload
    assert (dist / "verify_output.py").is_file()


def test_flattened_output_collisions_are_rejected_without_mutating_dist(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    (outputs / "a").mkdir(parents=True)
    (outputs / "b").mkdir()
    dist.mkdir()
    (outputs / "a" / "feed.txt").write_text("vless://id@example.test:443#one\n")
    (outputs / "b" / "feed.txt").write_text("vless://id@example.test:443#two\n")
    (dist / "old.txt").write_text("safe")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)
    with pytest.raises(RuntimeError, match="Conflicting generated output filename"):
        verifier.main()
    assert (dist / "old.txt").read_text() == "safe"


def test_symlinked_generated_artifact_is_rejected_without_mutating_dist(tmp_path, monkeypatch):
    verifier = _load_verify_output()
    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist"
    outputs.mkdir()
    dist.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("should-not-be-published")
    try:
        (outputs / "feed.txt").symlink_to(secret)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks unavailable on this filesystem")
    (dist / "old.txt").write_text("safe")
    monkeypatch.setattr(verifier, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(verifier, "DIST_DIR", dist)
    with pytest.raises(RuntimeError, match="Refusing symlinked generated output"):
        verifier.main()
    assert (dist / "old.txt").read_text() == "safe"
