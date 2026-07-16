from pathlib import Path


def test_production_workflow_preserves_complete_residue():
    workflow = Path(".github/workflows/huntx.yml").read_text()
    assert "pull_request:" in workflow
    assert "timeout-minutes: 115" in workflow
    assert 'HUNTX_RUN_TIMEOUT: "5400"' in workflow
    assert "timeout --signal=TERM --kill-after=60s 105m" in workflow
    assert 's3://$S3_BUCKET/raw' in workflow
    assert "scripts/checkpoint_runtime_state.py" in workflow
    assert "!cancelled()" not in workflow

    raw_upload = workflow.index(
        'aws s3 sync persist/data/raw "s3://$S3_BUCKET/raw"'
    )
    state_upload = workflow.index(
        'aws s3 cp persist/state.db "s3://$S3_BUCKET/$next_key"'
    )
    assert raw_upload < state_upload
