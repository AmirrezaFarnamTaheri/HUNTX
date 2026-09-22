from __future__ import annotations

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
