"""Recovery must be triggerable by a verified main update if schedules stall."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github/workflows/huntx-schedule-watchdog.yml"


def test_watchdog_has_main_push_fallback_without_publishing_directly():
    events = yaml.load(WATCHDOG.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)["on"]
    assert "schedule" in events
    assert "workflow_dispatch" in events
    assert "push" in events
    push = events["push"]
    assert push["branches"] == ["main"]
    assert ".github/workflows/huntx-schedule-watchdog.yml" in push["paths"]
    assert ".github/workflows/huntx.yml" in push["paths"]
    assert "src/huntx/**" in push["paths"]


def test_push_recovery_reuses_active_run_and_staleness_guards():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "production_active" in source
    assert "recovery_active" in source
    assert 'if (( age_seconds >= 8400 )); then' in source
    assert "huntx-recovery-orchestrator.yml/dispatches" in source
    # A push must never skip through the downstream producer authentication gates.
    assert "publish-generated-outputs.yml/dispatches" not in source
