"""Large legitimate subscriptions must never be treated as failed or truncated.

The per-file transform setting is a *transactional write chunk size*, not an
upper bound on distinct observed proxies. Global run-budget exhaustion remains
fail-closed and must retain the file pending for a future larger run.
"""
from unittest.mock import MagicMock, patch

import pytest

from huntx.pipeline.transform import TransformPipeline
from huntx.pipeline.optimized_transform import OptimizedTransformPipeline


def make_pipeline(monkeypatch, cls, *, count=201):
    monkeypatch.setenv("HUNTX_TRANSFORM_MAX_RECORDS_PER_FILE", "100")
    raw = MagicMock()
    raw.get.return_value = b"synthetic source"
    repo = MagicMock()
    conn = MagicMock()
    repo.db.connect.return_value.__enter__.return_value = conn
    repo.db.connect.return_value.__exit__.return_value = False
    registry = MagicMock()
    parser = MagicMock()
    parser.parse.return_value = [
        {"unique_hash": f"unique-{i}", "data": {"line": f"example-{i}"}}
        for i in range(count)
    ]
    registry.get.return_value = parser
    pipeline = cls(raw, repo, registry, max_workers=2)
    observation = {"id": 7, "raw_hash": "raw-hash", "source_id": "approved",
                   "filename": "large.conf", "file_size": 120_000}
    repo.get_pending_files.side_effect = [[observation], []]
    return pipeline, repo, observation


@pytest.mark.parametrize("pipeline_type", [TransformPipeline, OptimizedTransformPipeline])
def test_all_distinct_rows_survive_per_file_write_limit(monkeypatch, pipeline_type):
    pipeline, repo, _ = make_pipeline(monkeypatch, pipeline_type)
    with patch("huntx.pipeline.transform.decide_format", return_value="conf_lines"):
        summary = pipeline.process_pending(max_records=300)
    assert summary["completed"] is True
    assert summary["processed"] == 1
    assert summary["failed"] == 0
    assert summary["records"] == 201
    batches = [call.args[0] for call in repo.add_records_batch.call_args_list]
    assert [len(batch) for batch in batches] == [100, 100, 1]
    assert {row[3] for batch in batches for row in batch} == {
        f"unique-{i}" for i in range(201)
    }
    repo.update_observation_status_batch.assert_called_once()
    assert repo.update_observation_status_batch.call_args.args[0] == [
        ("processed", None, 7)
    ]
    # Atomicity: every insert chunk and the source acknowledgement use
    # the same outer transaction.
    connection = repo.db.connect.return_value.__enter__.return_value
    for call in repo.add_records_batch.call_args_list:
        assert call.kwargs["conn"] is connection
    assert repo.update_observation_status_batch.call_args.kwargs["conn"] is connection
    assert repo.db.connect.call_count == 1


@pytest.mark.parametrize("pipeline_type", [TransformPipeline, OptimizedTransformPipeline])
def test_oversize_for_global_run_budget_is_never_silently_acknowledged(
    monkeypatch, pipeline_type
):
    pipeline, repo, _ = make_pipeline(monkeypatch, pipeline_type)
    with patch("huntx.pipeline.transform.decide_format", return_value="conf_lines"):
        with pytest.raises(RuntimeError, match="exceeding HUNTX_TRANSFORM_MAX_RECORDS"):
            pipeline.process_pending(max_records=150)
    repo.add_records_batch.assert_not_called()
    repo.update_observation_status_batch.assert_not_called()


def test_later_insert_chunk_failure_cannot_ack_partial_source(monkeypatch):
    pipeline, repo, observation = make_pipeline(monkeypatch, TransformPipeline)
    repo.add_records_batch.side_effect = [None, RuntimeError("write failed")]
    with patch("huntx.pipeline.transform.decide_format", return_value="conf_lines"):
        with pytest.raises(RuntimeError, match="write failed"):
            pipeline.process_pending(max_records=300)
    repo.update_observation_status_batch.assert_not_called()
    assert repo.add_records_batch.call_count == 2
    assert observation["id"] == 7
    # The DB context manager must roll back the transaction on exception.
    assert repo.db.connect.return_value.__exit__.call_args.args[0] is RuntimeError
