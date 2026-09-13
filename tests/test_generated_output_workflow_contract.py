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


def test_main_mirror_is_inventory_scoped_and_never_force_pushed():
    workflow = _workflow()

    assert "scripts/sync_generated_outputs_to_main.py" in workflow
    assert ".github/huntx-generated-files.txt" in workflow
    assert "git push origin HEAD:refs/heads/main" in workflow
    main_mirror = workflow[workflow.index("- name: Mirror verified outputs to main") :]
    assert "--force" not in main_mirror
    assert "test -f scripts/verify_output.py" in main_mirror


def test_control_plane_push_republishes_latest_trusted_producer_without_recursion():
    workflow = _workflow()
    trigger = workflow[: workflow.index("permissions:")]

    assert "  push:" in trigger
    assert "      - main" in trigger
    assert '      - ".github/workflows/publish-generated-outputs.yml"' in trigger
    assert '      - ".github/huntx-generated-files.txt"' in trigger
    assert '      - "scripts/assemble_generated_snapshot.py"' in trigger
    assert '      - "scripts/sync_generated_outputs_to_main.py"' in trigger
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
