from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from huntx.pipeline.build import BuildPipeline


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_authorization_uses_exact_observation_only() -> None:
    repo = source("src/huntx/state/repo.py")
    verdict = source("src/huntx/state/verdict_store.py")
    assert "JOIN seen_files s ON r.source_observation_id = s.id" in repo
    assert "JOIN seen_files s ON r.source_observation_id = s.id" in verdict
    assert "r.source_file_hash = s.raw_hash" not in repo[repo.index("def get_records_for_build"):repo.index("def is_artifact_published")]
    assert "r.source_file_hash = s.raw_hash" not in verdict[verdict.index("def get_records_for_governed_build"):]


def test_build_handler_failure_escapes_route_worker() -> None:
    state_repo = Mock()
    artifact_store = Mock()
    registry = Mock()
    state_repo.get_records_for_build.return_value = [
        {"record_type": "fmt1", "data": "value"}
    ]
    handler = Mock()
    handler.build.side_effect = ValueError("boom")
    registry.get.return_value = handler
    pipeline = BuildPipeline(state_repo, artifact_store, registry)
    with pytest.raises(RuntimeError, match="Route route1 build failed"):
        pipeline.run(
            {"name": "route1", "formats": ["fmt1"], "from_sources": ["src1"]}
        )


def test_release_status_is_decided_before_export() -> None:
    orch = source("src/huntx/core/hardened_orchestrator.py")
    assert 'status = "partial"' in orch[orch.index("for completed_build in done:"):orch.index("pending_publish:")]
    assert 'status = "partial"' in orch[orch.index("for completed_publish in done:"):orch.index("should_export =")]
    assert orch.index("_classify_completed_status(", orch.index("route_destinations")) < orch.index("should_export =")


def test_global_deadline_is_wired_through_mutation_workers() -> None:
    deadline = source("src/huntx/core/deadline.py")
    build = source("src/huntx/pipeline/build.py")
    governed = source("src/huntx/pipeline/governed_build.py")
    publish = source("src/huntx/pipeline/publish.py")
    telegram = source("src/huntx/publishers/telegram/publisher.py")
    orch = source("src/huntx/core/hardened_orchestrator.py")
    assert "class DeadlineExceeded" in deadline
    assert "deadline: Deadline | None = None" in build
    assert "deadline: Deadline | None = None" in governed
    assert "deadline: Deadline | None = None" in publish
    assert "deadline: Deadline | None = None" in telegram
    assert "deadline=deadline" in orch
    assert "shutdown(wait=True, cancel_futures=True)" in orch
    assert "deadline.clamp_timeout(60.0)" in telegram
    assert "deadline.sleep(" in telegram


def test_publication_history_write_is_idempotent() -> None:
    repo = source("src/huntx/state/repo.py")
    block = repo[repo.index("def mark_published"):repo.index("def ensure_publication_intent")]
    assert "WHERE NOT EXISTS" in block
    assert "route_name = ? AND artifact_hash = ?" in block


def test_unknown_callbacks_fail_closed_and_telegram_errors_are_sanitized() -> None:
    handlers = source("src/huntx/bot/handlers.py")
    telegram = source("src/huntx/publishers/telegram/publisher.py")
    assert 'await event.answer("Invalid action", alert=True)' in handlers
    assert "def _safe_telegram_error(" in telegram
    assert "type(e).__name__" in telegram
