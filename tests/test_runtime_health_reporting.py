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


def test_fallback_success_without_report_is_degraded():
    module = _load_module()
    disposition, reasons = module._fallback_disposition(0, True)
    assert disposition == "degraded"
    assert "did not produce a structured report" in reasons[0]


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


def test_normalize_reasons_handles_untrusted_json_shapes():
    module = _load_module()
    assert module._normalize_reasons("one reason") == ["one reason"]
    assert module._normalize_reasons(["one", 2]) == ["one", "2"]
    assert module._normalize_reasons({"bad": "shape"}) == ["invalid reasons type: dict"]
    assert module._normalize_reasons(42) == ["invalid reasons type: int"]


def test_inventory_is_memory_bounded_but_counts_every_file(tmp_path):
    module = _load_module()
    for index in range(module._MAX_INVENTORY_ITEMS + 25):
        path = tmp_path / f"item-{index:04d}.txt"
        path.write_text("abc", encoding="utf-8")

    rows, file_count, total_bytes = module._inventory(tmp_path)

    assert len(rows) == module._MAX_INVENTORY_ITEMS
    assert file_count == module._MAX_INVENTORY_ITEMS + 25
    assert total_bytes == file_count * 3
    assert rows == sorted(rows)
