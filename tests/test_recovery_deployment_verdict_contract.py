"""A recovery orchestrator must not call skipped publication a restored release."""

from pathlib import Path


WORKFLOW = Path(".github/workflows/huntx-recovery-orchestrator.yml")


def _verification_job() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    return source.split(
        "- name: Verify all downstream recovery consumers", 1
    )[1].split("- name: Record recovery result", 1)[0]


def test_recovery_checks_producer_release_artifact_not_just_job_success():
    source = _verification_job()
    assert "SOURCE_RUN_ID: ${{ steps.production.outputs.run_id }}" in source
    assert "SOURCE_RUN_ATTEMPT: ${{ steps.production_result.outputs.run_attempt }}" in source
    assert 'artifacts?per_page=100' in source
    assert 'huntx-output-${SOURCE_RUN_ID}-${SOURCE_RUN_ATTEMPT}' in source
    assert 'No eligible production release' in source


def test_recovery_requires_pages_deploy_step_success_before_reporting_restoration():
    source = _verification_job()
    assert 'jobs?per_page=100' in source
    assert 'Deploy cumulative dashboard to Pages' in source
    assert 'Publisher skipped Pages deployment' in source
    # The restoration proof must happen before the terminal success verdict.
    assert source.index("Publisher skipped Pages deployment") < source.index(
        "All explicit recovery downstream consumers completed successfully."
    )


def test_recovery_reports_no_release_distinctly_from_success():
    source = _verification_job()
    assert 'Recovery did not restore a fresh publication' in source
    assert 'publisher' in source.lower()
