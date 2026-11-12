"""The OS watchdog must bound non-cooperative build workers after deadline."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "huntx.yml"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_hung_build_can_extend_global_deadline_by_at_most_two_minutes():
    workflow = _workflow()
    grace = int(workflow["env"]["HUNTX_SHUTDOWN_GRACE_SECONDS"])
    assert 15 <= grace <= 90

    source = WORKFLOW.read_text(encoding="utf-8")
    watchdog = source.split("- name: Run HuntX with controlled watchdog", 1)[1].split(
        "- name: Verify and package recoverable output", 1
    )[0]
    assert "watchdog_budget_seconds=$((HUNTX_RUN_TIMEOUT + HUNTX_SHUTDOWN_GRACE_SECONDS))" in watchdog
    assert 'timeout --signal=TERM --kill-after=20s "${watchdog_budget_seconds}s"' in watchdog
    assert '"$HUNTX_SHUTDOWN_GRACE_SECONDS" =~ ^[1-9][0-9]*$' in watchdog
    assert "HUNTX_SHUTDOWN_GRACE_SECONDS > 90" in watchdog


def test_watchdog_failure_still_records_exit_and_persists_checkpoint():
    source = WORKFLOW.read_text(encoding="utf-8")
    runtime = source.split("- name: Run HuntX with controlled watchdog", 1)[1].split(
        "- name: Verify and package recoverable output", 1
    )[0]
    assert "rc=${PIPESTATUS[0]}" in runtime
    assert 'echo "exit_code=$rc" >> "$GITHUB_OUTPUT"' in runtime
    assert "id: checkpoint" in source
    assert "always() && !cancelled() && needs.run.outputs.checkpoint_ready == 'true'" in source
