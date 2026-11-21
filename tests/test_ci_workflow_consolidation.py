"""Contract tests for HUNTX's single, comprehensive change-validation run."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI_PATH = WORKFLOWS / "pr-validation.yml"


def _ci():
    # BaseLoader preserves the GitHub Actions "on" key (a YAML 1.1 boolean).
    return yaml.load(CI_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _commands(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_one_workflow_runs_all_change_validation_gates():
    ci = _ci()
    jobs = ci["jobs"]
    required = {
        "workflows",
        "go",
        "deploy-manifests",
        "frontend",
        "python",
        "dependency-audit",
        "dev-outputs",
    }
    assert required <= set(jobs)
    assert jobs["validate"]["name"] == "quality-gate"
    assert "always()" in jobs["validate"]["if"]
    assert set(jobs["validate"]["needs"]) == set(jobs) - {"validate"}


def test_validation_is_triggered_for_prs_pushes_manual_and_daily_security():
    triggers = _ci()["on"]
    assert {"pull_request", "push", "workflow_dispatch", "schedule"} <= set(triggers)
    assert "23 5 * * *" in {item["cron"] for item in triggers["schedule"]}
    assert not (WORKFLOWS / "go-security.yml").exists()
    assert not (WORKFLOWS / "dev-output-refresh.yml").exists()


def test_migrated_go_security_and_dev_telemetry_checks_remain_enforced():
    jobs = _ci()["jobs"]
    go = _commands(jobs["go"])
    dev = _commands(jobs["dev-outputs"])
    assert go.count("govulncheck@v1.7.0") >= 2
    assert "go test -race ./..." in go
    assert "src/huntx/connectors/v2ray_collector" in go
    assert "stage_legacy_release_fixture" in dev
    assert "python scripts/verify_dashboard_telemetry.py" in dev
    assert "tests/test_output_telemetry_coverage.py" in dev
