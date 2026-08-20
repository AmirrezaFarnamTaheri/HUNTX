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
    nekobox.write_text(json.dumps([{"type": "vless", "tag": "node"}]), encoding="utf-8")

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
