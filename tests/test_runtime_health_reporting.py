import importlib.util
import json
from pathlib import Path


SCRIPT = Path("scripts/report_runtime_health.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("report_runtime_health", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fallback_timeout_is_degraded_when_checkpoint_exists():
    module = _load_module()
    disposition, reasons = module._fallback_disposition(124, True)
    assert disposition == "degraded"
    assert "recoverable checkpoint" in reasons[0]


def test_fallback_non_timeout_failure_is_fatal():
    module = _load_module()
    disposition, reasons = module._fallback_disposition(1, True)
    assert disposition == "fatal"
    assert "code 1" in reasons[0]


def test_load_report_rejects_invalid_json(tmp_path):
    module = _load_module()
    path = tmp_path / "run-summary.json"
    path.write_text("not json", encoding="utf-8")
    payload, error = module._load_report(path)
    assert payload is None
    assert error is not None
    assert "unreadable" in error


def test_load_report_accepts_structured_health(tmp_path):
    module = _load_module()
    path = tmp_path / "run-summary.json"
    expected = {"disposition": "degraded", "status": "partial", "metrics": {"ingest_err": 2}}
    path.write_text(json.dumps(expected), encoding="utf-8")
    payload, error = module._load_report(path)
    assert error is None
    assert payload == expected
