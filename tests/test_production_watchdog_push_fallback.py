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


def test_watchdog_recovers_when_latest_completed_production_has_old_source_commit():
    """A new commit must not wait for 2h20m if its release is not produced."""
    source = WATCHDOG.read_text(encoding="utf-8")
    assert 'latest_sha="$(jq -r' in source
    assert 'if [[ "$latest_sha" != "$GITHUB_SHA" ]]; then' in source
    assert "Production source revision stale" in source
    # Active production/recovery checks must remain ahead of dispatch.
    assert source.index("production_active") < source.index("Production source revision stale")
    assert source.index("recovery_active") < source.index("Production source revision stale")


def test_watchdog_main_pushes_cover_publisher_and_ui_artifact_fixes():
    events = yaml.load(WATCHDOG.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)["on"]
    paths = events["push"]["paths"]
    for required in (
        "scripts/assemble_generated_snapshot.py",
        "scripts/validate_pages_package.py",
        "docs/assets/js/**",
        ".github/workflows/publish-generated-outputs.yml",
    ):
        assert required in paths

