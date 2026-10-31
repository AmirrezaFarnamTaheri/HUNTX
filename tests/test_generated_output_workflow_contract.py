from pathlib import Path


def _workflow() -> str:
    return Path(".github/workflows/publish-generated-outputs.yml").read_text()


def test_generated_publication_preserves_commit_history_and_cumulative_parent():
    workflow = _workflow()

    assert "Restore previous generated snapshot" in workflow
    assert 'RESTORED_SHA: ${{ steps.previous.outputs.sha }}' in workflow
    assert 'if [[ "$remote_sha" != "$RESTORED_SHA" ]]' in workflow
    assert 'git checkout -B generated-outputs-next "$remote_sha"' in workflow
    assert "git checkout --orphan generated-outputs-next" in workflow
    assert workflow.index('git checkout -B generated-outputs-next "$remote_sha"') < workflow.index(
        "git checkout --orphan generated-outputs-next"
    )
    assert "--force-with-lease=\"refs/heads/generated-outputs:${remote_sha}\"" in workflow


def test_production_publisher_never_commits_generated_data_to_main():
    workflow = _workflow()

    assert "Mirror verified outputs to main" not in workflow
    assert "git push origin HEAD:refs/heads/main" not in workflow
    assert "Validate resulting main head" not in workflow
    assert "--force-with-lease=\"refs/heads/generated-outputs:" in workflow
    assert "actions/deploy-pages@" in workflow
    assert "Deploy cumulative dashboard to Pages" in workflow
    assert r"Source-branch mirrors: \`none\`" in workflow


def test_control_plane_push_republishes_latest_trusted_producer_without_recursion():
    workflow = _workflow()
    trigger = workflow[: workflow.index("permissions:")]

    assert "  push:" in trigger
    assert "      - main" in trigger
    assert '      - ".github/workflows/publish-generated-outputs.yml"' in trigger
    assert '      - ".github/huntx-generated-files.txt"' not in trigger
    assert '      - "scripts/assemble_generated_snapshot.py"' in trigger
    assert '      - "scripts/sync_generated_outputs_to_main.py"' not in trigger
    assert "outputs/**" not in trigger
    assert "outputs_dev/**" not in trigger

    assert "github.event_name == 'push'" in workflow
    assert "github.rest.actions.listWorkflowRuns" in workflow
    assert "workflow_id: 'huntx.yml'" in workflow
    assert "branch: 'main'" in workflow
    assert "status: 'completed'" in workflow
    assert "candidate.conclusion !== 'success'" in workflow
    assert "candidate.path !== expectedPath" in workflow
    assert "candidate.name !== 'huntx-production'" in workflow
    assert "candidate.head_sha !== context.sha" in workflow
    assert "Unsupported publication event" in workflow


def test_control_plane_push_requires_unexpired_publication_artifacts():
    workflow = _workflow()

    assert "github.rest.actions.listWorkflowRunArtifacts" in workflow
    assert ".filter(artifact => !artifact.expired)" in workflow
    assert "runtime-checkpoint-${run.id}-${run.run_attempt}" in workflow
    assert "huntx-output-${run.id}-${run.run_attempt}" in workflow
    assert "huntx-logs-${run.id}-${run.run_attempt}" in workflow
    assert "missing or expired publication artifacts" in workflow
    assert "core.setOutput('ready', 'false')" in workflow
    assert "steps.source.outputs.ready == 'true'" in workflow


def test_stale_source_artifacts_are_validated_before_any_publication_write():
    workflow = _workflow()
    preflight = workflow.index("- name: Validate producer client artifacts against current contracts")
    assert preflight < workflow.index("- name: Build verified dashboard data from release dist")
    assert preflight < workflow.index("- name: Commit atomic generated-only snapshot")
    assert "from scripts.verify_output import validate_file" in workflow
    assert 'stats.get("invalid") or stats.get("type") == "empty"' in workflow


def test_pr_validation_covers_generated_artifacts_and_dependency_configuration():
    gate = Path(".github/workflows/pr-validation.yml").read_text()
    assert gate.count('      - ".github/**"') == 2
    assert gate.count('      - "outputs/**"') == 2
    assert gate.count('      - "outputs_dev/**"') == 2


def test_publisher_rejects_obsolete_producer_replay_and_changed_main_code():
    workflow = _workflow()
    assert 'github.rest.repos.getBranch' in workflow
    assert 'github.rest.repos.compareCommits' in workflow
    assert "comparison.data.status === 'ahead'" in workflow
    assert 'files.length < 300' in workflow
    assert "filename.startsWith('outputs/')" in workflow
    assert "filename.startsWith('docs/artifacts/')" in workflow
    assert "filename === 'docs/assets/js/data.js'" in workflow
    assert "path: 'manifests/publication.json'" in workflow
    assert "ref: 'generated-outputs'" in workflow
    assert 'runId < priorId' in workflow
    assert 'expectedAttempt < priorAttempt' in workflow
    authorized = workflow.index("core.setOutput('ready', 'true')")
    assert workflow.index("github.rest.repos.getBranch") < authorized
    assert workflow.index("path: 'manifests/publication.json'") < authorized


def test_new_local_generated_output_payloads_are_ignored_by_git():
    """Legacy tracked artifacts are separate from future untracked data."""
    import subprocess

    for relative in (
        "outputs/huntx-probe-untracked.txt",
        "outputs_dev/huntx-probe-untracked.json",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", relative],
            check=False,
            capture_output=True,
        )
        assert result.returncode == 0, relative
