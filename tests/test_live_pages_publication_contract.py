"""Live deployment must be verified before a publication is called restored.

Both the Pages archive and generated ledger may be valid while the public
CDN still serves stale or incomplete content (#201).
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / ".github" / "workflows" / "publish-generated-outputs.yml"
RECOVERY = ROOT / ".github" / "workflows" / "huntx-recovery-orchestrator.yml"


def test_publisher_checks_served_payload_before_generated_ledger():
    workflow = PUBLISHER.read_text(encoding="utf-8")
    deployment = workflow.index("- name: Deploy cumulative dashboard to Pages")
    proof = workflow.index("- name: Verify public Pages snapshot integrity")
    git_commit = workflow.index("- name: Commit atomic generated-only snapshot")
    assert deployment < proof < git_commit
    assert "id: live" in workflow[proof:git_commit]
    assert "scripts/verify_deployed_pages.py" in workflow[proof:git_commit]
    assert "steps.deployment.outputs.page_url" in workflow[proof:git_commit]
    assert "steps.live.outcome == 'success'" in workflow[git_commit:]


def test_recovery_requires_verified_live_site_not_just_deploy_success():
    source = RECOVERY.read_text(encoding="utf-8")
    block = source.split("- name: Verify all downstream recovery consumers", 1)[1].split(
        "- name: Record recovery result", 1
    )[0]
    assert 'select(.name == "Verify public Pages snapshot integrity" and .conclusion == "success")' in block
    assert "Publisher did not verify live Pages" in block
    assert block.index("Publisher did not verify live Pages") < block.index(
        "All explicit recovery downstream consumers completed successfully."
    )
