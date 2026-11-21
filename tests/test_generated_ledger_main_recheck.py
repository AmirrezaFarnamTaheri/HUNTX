"""The generated ledger must not advance after main source drift."""

from pathlib import Path


WORKFLOW = Path(".github/workflows/publish-generated-outputs.yml")


def test_main_source_revision_is_rechecked_immediately_before_generated_push():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    commit = workflow.split(
        "- name: Commit atomic generated-only snapshot", 1
    )[1].split("- name: Summarize publication", 1)[0]

    assert "SOURCE_MAIN_SHA: ${{ steps.source.outputs.main_sha }}" in commit
    assert "git ls-remote --heads origin refs/heads/main" in commit
    assert "Main changed before generated snapshot push" in commit
    assert commit.index("git ls-remote --heads origin refs/heads/main") < commit.index(
        "git push origin HEAD:refs/heads/generated-outputs"
    )
