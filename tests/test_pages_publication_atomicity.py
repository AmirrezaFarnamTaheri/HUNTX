"""Publication ledger must not advance before Pages has deployed its snapshot."""

from pathlib import Path


SOURCE = Path(".github/workflows/publish-generated-outputs.yml")


def test_pages_deploy_precedes_generated_branch_ledger_advancement():
    workflow = SOURCE.read_text(encoding="utf-8")
    steps = [
        "- name: Recheck complete published proxy inventory",
        "- name: Finalize publisher proof before upload",
        "- name: Upload cumulative dashboard to Pages",
        "- name: Revalidate main before Pages deployment",
        "- name: Deploy cumulative dashboard to Pages",
        "- name: Commit atomic generated-only snapshot",
    ]
    for before, after in zip(steps, steps[1:]):
        assert workflow.index(before) < workflow.index(after), (before, after)


def test_publisher_finalizes_authentication_in_exact_uploaded_snapshot():
    workflow = SOURCE.read_text(encoding="utf-8")
    finalize_step = workflow.split(
        "- name: Finalize publisher proof before upload", 1
    )[1].split("- name: Configure Pages deployment", 1)[0]
    assert "publisher_live_attestation.py finalize" in finalize_step
    assert "--producer-receipt" in finalize_step
    assert 'test -s "$SOURCE_ROOT/snapshot/manifests/SHA256SUMS"' in finalize_step

    commit_step = workflow.split(
        "- name: Commit atomic generated-only snapshot", 1
    )[1].split("- name: Summarize publication", 1)[0]
    assert "publisher_live_attestation.py finalize" not in commit_step
    assert "--force-with-lease=" in commit_step


def test_pages_deployment_failure_prevents_ledger_commit():
    workflow = SOURCE.read_text(encoding="utf-8")
    assert "- name: Deploy cumulative dashboard to Pages" in workflow
    assert "id: deployment" in workflow
    assert "if: steps.release.outputs.ready == 'true' && steps.deployment.outcome == 'success'" in workflow
