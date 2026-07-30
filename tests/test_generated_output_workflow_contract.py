from pathlib import Path


def test_generated_publication_preserves_commit_history_and_cumulative_parent():
    workflow = Path(".github/workflows/publish-generated-outputs.yml").read_text()

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
    workflow = Path(".github/workflows/publish-generated-outputs.yml").read_text()

    assert "scripts/sync_generated_outputs_to_main.py" in workflow
    assert ".github/huntx-generated-files.txt" in workflow
    assert "git push origin HEAD:refs/heads/main" in workflow
    main_mirror = workflow[workflow.index("- name: Mirror verified outputs to main") :]
    assert "--force" not in main_mirror
    assert "test -f outputs/verify_output.py" in main_mirror
