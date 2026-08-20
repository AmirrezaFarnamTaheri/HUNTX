import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from huntx.config.loader import load_config
from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishingConfig,
    PublishRoute,
    SourceConfig,
    SourceSelector,
    TelegramSourceConfig,
    normalize_destination_mode,
)
from huntx.config.validate import validate_config
from huntx.core.hardened_orchestrator import HardenedOrchestrator, _classify_completed_status
from huntx.pipeline.publish import PublishPipeline


def test_post_on_change_is_normalized_to_telegram_transport():
    destination = DestinationConfig(chat_id="-1001", mode="post_on_change")

    assert destination.mode == "telegram"
    assert normalize_destination_mode(" POST_ON_CHANGE ") == "telegram"


def test_unknown_destination_mode_is_rejected_at_load_time():
    for invalid_mode in ("bundle", "", False, 0):
        with pytest.raises(ValidationError, match="Unsupported destination mode"):
            DestinationConfig(chat_id="-1001", mode=invalid_mode)


def test_production_config_legacy_mode_loads_as_canonical_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test-hash")
    monkeypatch.setenv("TELEGRAM_USER_SESSION", "test-session")

    config = load_config(Path("configs/config.prod.yaml"))

    assert config.routes
    assert all(destination.mode == "telegram" for route in config.routes for destination in route.destinations)


def test_strict_validation_uses_runtime_publish_token_precedence(monkeypatch):
    monkeypatch.setenv("HUNTX_STRICT", "1")
    monkeypatch.setenv("PUBLISH_BOT_TOKEN", "123456:publish-token")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    config = AppConfig(
        sources=[
            SourceConfig(
                id="source",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123456:source-token", chat_id="-1001"),
            )
        ],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="route",
                    from_sources=["source"],
                    formats=["npvt"],
                    destinations=[DestinationConfig(chat_id="-1002", mode="telegram")],
                )
            ]
        ),
    )

    validate_config(config)


class _FakeStateRepo:
    def __init__(self):
        self.confirmed = False
        self.completed = False
        self.published = False

    def ensure_publication_intent(self, unique_id, artifact_hash, *, generation):
        return 1

    def get_delivery_state(self, intent_id, destination_id):
        return None

    def mark_delivery_sending(self, intent_id, destination_id):
        return None

    def mark_delivery_confirmed(self, intent_id, destination_id, *, remote_receipt=None):
        self.confirmed = True

    def mark_delivery_failed(self, intent_id, destination_id, *, error_class, unknown_outcome):
        raise AssertionError(f"unexpected publication failure: {error_class}")

    def is_delivery_confirmed(self, intent_id, destination_id):
        return self.confirmed

    def complete_publication_intent(self, intent_id):
        self.completed = True

    def mark_published(self, unique_id, artifact_hash):
        self.published = True


class _FakePublisher:
    def publish(self, chat_id, data, filename, caption):
        return "receipt-1"


def test_publish_pipeline_defensively_accepts_legacy_mode(monkeypatch):
    monkeypatch.setenv("PUBLISH_BOT_TOKEN", "123456:publish-token")
    repo = _FakeStateRepo()
    pipeline = PublishPipeline(repo)
    pipeline._publisher_for = lambda token: (_FakePublisher(), __import__("threading").Lock())
    payload = b"vmess://example"

    published = pipeline.run(
        {
            "route_name": "all_sources",
            "unique_id": "all_sources:npvt",
            "format": "npvt",
            "data": payload,
            "artifact_hash": hashlib.sha256(payload).hexdigest(),
        },
        [
            {
                "chat_id": "-1002",
                "mode": "post_on_change",
                "caption_template": "Updated {timestamp}",
            }
        ],
    )

    assert published is True
    assert repo.confirmed is True
    assert repo.completed is True
    assert repo.published is True


def test_minority_source_errors_do_not_invalidate_successful_release():
    assert (
        _classify_completed_status(
            ingest_ok=67,
            ingest_err=8,
            failed_routes=0,
            publish_failures=0,
        )
        == "completed"
    )
    assert (
        _classify_completed_status(
            ingest_ok=51,
            ingest_err=49,
            failed_routes=0,
            publish_failures=0,
        )
        == "completed"
    )


def test_tied_or_majority_source_failures_are_partial():
    assert (
        _classify_completed_status(
            ingest_ok=50,
            ingest_err=50,
            failed_routes=0,
            publish_failures=0,
        )
        == "partial"
    )
    assert (
        _classify_completed_status(
            ingest_ok=1,
            ingest_err=99,
            failed_routes=0,
            publish_failures=0,
        )
        == "partial"
    )


def test_all_source_failures_are_fatal():
    assert (
        _classify_completed_status(
            ingest_ok=0,
            ingest_err=8,
            failed_routes=0,
            publish_failures=0,
        )
        == "failed"
    )
    assert (
        _classify_completed_status(
            ingest_ok=0,
            ingest_err=0,
            failed_routes=0,
            publish_failures=0,
        )
        == "failed"
    )


def test_route_or_publish_failure_remains_partial():
    assert (
        _classify_completed_status(
            ingest_ok=67,
            ingest_err=0,
            failed_routes=1,
            publish_failures=0,
        )
        == "partial"
    )
    assert (
        _classify_completed_status(
            ingest_ok=67,
            ingest_err=0,
            failed_routes=0,
            publish_failures=1,
        )
        == "partial"
    )


def test_full_release_completes_with_minority_degraded_sources():
    config = AppConfig(
        sources=[
            SourceConfig(
                id="healthy_a",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123456:source-token", chat_id="-1001"),
            ),
            SourceConfig(
                id="healthy_b",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123456:source-token", chat_id="-1002"),
            ),
            SourceConfig(
                id="degraded",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123456:source-token", chat_id="-1003"),
            ),
        ],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="route",
                    from_sources=["healthy_a", "healthy_b", "degraded"],
                    formats=["npvt"],
                    destinations=[DestinationConfig(chat_id="-1004", mode="telegram")],
                )
            ]
        ),
    )
    payload = b"vmess://example"
    build_result = {
        "route_name": "route",
        "unique_id": "route:npvt",
        "format": "npvt",
        "data": payload,
        "artifact_hash": hashlib.sha256(payload).hexdigest(),
    }

    orchestrator = object.__new__(HardenedOrchestrator)
    orchestrator.config = config
    orchestrator.max_workers = 3
    orchestrator.repo = object()
    orchestrator._get_seen_file_max_id = lambda: 0

    async def ingest_worker(queue, results, result_lock):
        while not queue.empty():
            source = await queue.get()
            async with result_lock:
                results["err" if source.id == "degraded" else "ok"] += 1
            queue.task_done()

    orchestrator._worker_async = ingest_worker
    orchestrator.transform_pipeline = SimpleNamespace(
        process_pending=lambda **kwargs: {
            "completed": True,
            "stop_reason": "complete",
        }
    )
    orchestrator.build_pipeline = SimpleNamespace(run=lambda route, **kwargs: [build_result])
    orchestrator.publish_pipeline = SimpleNamespace(run=lambda result, destinations, **kwargs: True)
    orchestrator._export_outputs = lambda results: None
    orchestrator._export_dev_outputs = lambda results: None
    orchestrator.raw_store = SimpleNamespace(
        prune_processed=lambda repo: None,
        prune_orphans=lambda repo: None,
    )
    orchestrator.artifact_store = SimpleNamespace(prune_archive=lambda: None)

    summary = asyncio.run(orchestrator._run_hardened(timeout=10, no_publish=False, allow_partial_export=False))

    assert summary["status"] == "completed"
    assert summary["ingest_ok"] == 2
    assert summary["ingest_err"] == 1
    assert summary["degraded_source_failures"] == 1
    assert summary["total_artifacts"] == 1
    assert summary["publish_attempts"] == 1
    assert summary["publish_failures"] == 0
