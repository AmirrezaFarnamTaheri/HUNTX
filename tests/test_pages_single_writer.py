"""Only the verified generated-outputs publisher may publish GitHub Pages.

Regression for #201: a production Pages deploy can race the cumulative
publisher and remove historical assets even when both jobs succeed.
"""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISHER = "publish-generated-outputs.yml"
PAGES_ACTIONS = {
    "actions/upload-pages-artifact",
    "actions/deploy-pages",
}


def _workflow_jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for job_name, job in (data or {}).get("jobs", {}).items():
            yield path.name, job_name, job


def test_exactly_one_pages_uploader_and_deployer_owned_by_verified_publisher():
    owners = []
    for workflow, job_name, job in _workflow_jobs():
        for step in job.get("steps", []):
            action = str(step.get("uses", "")).split("@", 1)[0]
            if action in PAGES_ACTIONS:
                owners.append((workflow, job_name, action))

    assert sorted(owners) == sorted([
        (PUBLISHER, "publish", "actions/upload-pages-artifact"),
        (PUBLISHER, "publish", "actions/deploy-pages"),
    ]), "A second Pages writer can overwrite a verified cumulative publication"


def test_github_pages_environment_only_appears_on_verified_publisher_job():
    owners = []
    for workflow, job_name, job in _workflow_jobs():
        environment = job.get("environment")
        name = environment.get("name") if isinstance(environment, dict) else environment
        if name == "github-pages":
            owners.append((workflow, job_name))
    assert owners == [(PUBLISHER, "publish")]


def test_producer_still_emits_eligible_release_and_recoverable_no_release_evidence():
    source = (WORKFLOWS / "huntx.yml").read_text(encoding="utf-8")
    assert "scripts/check_release_eligibility.py" in source
    assert "release-receipt.json" in source
    assert "huntx-no-release-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "runtime-checkpoint-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "huntx-output-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "persist-immutable-state" in source
    assert "source=restored" in source


def test_publisher_refuses_without_receipt_and_keeps_cumulative_history():
    source = (WORKFLOWS / PUBLISHER).read_text(encoding="utf-8")
    assert "--verify-receipt" in source
    assert "source_run_id" in source
    assert "previousPublication" in source
    assert "No fresh release" not in source or "no release" in source.lower()
    assert "Restore previous generated snapshot" in source
    assert "outputs_dev/_manifest.json.gz.index.json" in source
    assert "steps.source.outputs.ready == 'true'" in source
    assert "workflow_run:" in source
