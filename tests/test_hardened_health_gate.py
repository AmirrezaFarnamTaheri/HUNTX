from huntx.cli.hardened_main import _all_publish_failures_are_fatal


def test_complete_run_fails_when_all_publish_attempts_fail():
    summary = {
        "publish_attempts": 2,
        "publish_failures": 2,
        "ingestion_budget_exhausted": False,
    }
    assert _all_publish_failures_are_fatal(summary, no_publish=False)


def test_deadline_partial_preserves_outputs_when_publish_fails():
    summary = {
        "publish_attempts": 2,
        "publish_failures": 2,
        "ingestion_budget_exhausted": True,
    }
    assert not _all_publish_failures_are_fatal(summary, no_publish=False)


def test_no_publish_mode_never_fails_publish_gate():
    summary = {
        "publish_attempts": 2,
        "publish_failures": 2,
        "ingestion_budget_exhausted": False,
    }
    assert not _all_publish_failures_are_fatal(summary, no_publish=True)
