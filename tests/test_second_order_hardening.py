import asyncio
from types import SimpleNamespace

import pytest

from huntx.bot.interactive import InteractiveBot
from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishingConfig,
    PublishRoute,
    SourceConfig,
    SourceSelector,
    SourceTrustState,
    TelegramSourceConfig,
)
from huntx.config.validate import validate_config
from huntx.core.hardened_orchestrator import HardenedOrchestrator
from huntx.core import runtime_factory
from huntx.state.db import open_db
from huntx.state.repo import StateRepo


class _Event:
    def __init__(
        self,
        sender_id: int = 1,
        chat_id: int = 1,
        data=None,
        is_private=None,
    ):
        self.sender_id = sender_id
        self.chat_id = chat_id
        self.data = data
        self.is_private = is_private
        self.responses: list[str] = []
        self.answers: list[str] = []

    async def respond(self, message, **kwargs):
        self.responses.append(str(message))

    async def answer(self, message="", **kwargs):
        self.answers.append(str(message))


def _bot_with_db(tmp_path, monkeypatch):
    monkeypatch.delenv("HUNTX_ADMINS", raising=False)
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    bot.repo = StateRepo(bot.db)
    return bot


def test_pending_bot_user_cannot_retrieve_protected_artifacts(tmp_path, monkeypatch):
    bot = _bot_with_db(tmp_path, monkeypatch)
    bot._register_user("1", "1", "alice")
    event = _Event()

    assert asyncio.run(bot._require_approved(event)) is False
    assert event.responses
    assert "Approval required" in event.responses[-1]

    with bot.db.connect() as conn:
        conn.execute("UPDATE bot_users SET approved = 1 WHERE user_id = '1'")

    assert asyncio.run(bot._require_approved(_Event())) is True


def test_approved_bot_user_cannot_redirect_download_to_group(tmp_path, monkeypatch):
    bot = _bot_with_db(tmp_path, monkeypatch)
    bot._register_user("1", "1", "alice")
    with bot.db.connect() as conn:
        conn.execute("UPDATE bot_users SET approved = 1 WHERE user_id = '1'")

    group_event = _Event(sender_id=1, chat_id=-10099, is_private=False)
    assert asyncio.run(bot._require_approved(group_event)) is False
    assert group_event.responses
    assert "Private chat required" in group_event.responses[-1]


def test_register_user_does_not_erase_known_username(tmp_path, monkeypatch):
    bot = _bot_with_db(tmp_path, monkeypatch)
    assert bot._register_user("1", "1", "alice") is True
    assert bot._register_user("1", "1", None) is False

    assert bot._get_user_info("1")["username"] == "alice"


def test_legacy_group_delivery_row_is_not_active(tmp_path, monkeypatch):
    bot = _bot_with_db(tmp_path, monkeypatch)
    with bot.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (user_id, chat_id, username, registered_at, approved, muted)
            VALUES ('1', '-10099', 'alice', 0, 1, 0)
            """
        )
    assert bot._get_active_users() == []


def _runtime_config(*, candidate: bool = False) -> AppConfig:
    sources = [
        SourceConfig(
            id="approved",
            type="telegram",
            selector=SourceSelector(include_formats=["all"]),
            telegram=TelegramSourceConfig(token="123:source", chat_id="-1001"),
        )
    ]
    route_sources = ["approved"]
    if candidate:
        sources.append(
            SourceConfig(
                id="candidate",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123:source", chat_id="-1002"),
                trust_state=SourceTrustState.CANDIDATE,
            )
        )
        route_sources.append("candidate")

    return AppConfig(
        sources=sources,
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="route",
                    from_sources=route_sources,
                    formats=["npvt"],
                    destinations=[
                        DestinationConfig(
                            chat_id="-1003",
                            token="123:publish",
                        )
                    ],
                )
            ]
        ),
    )


def _bare_hardened(config: AppConfig):
    orchestrator = object.__new__(HardenedOrchestrator)
    orchestrator.config = config
    orchestrator.max_workers = 2
    orchestrator.repo = object()
    orchestrator._get_seen_file_max_id = lambda: 0

    async def ingest_worker(queue, results, lock):
        while not queue.empty():
            source = await queue.get()
            assert source.publication_eligible
            async with lock:
                results["ok"] += 1
            queue.task_done()

    orchestrator._worker_async = ingest_worker
    orchestrator.publish_pipeline = SimpleNamespace(run=lambda result, destinations: True)
    orchestrator._export_outputs = lambda results: None
    orchestrator._export_dev_outputs = lambda results: None
    orchestrator.raw_store = SimpleNamespace(
        prune_processed=lambda repo: None,
        prune_orphans=lambda repo: None,
    )
    orchestrator.artifact_store = SimpleNamespace(prune_archive=lambda: None)
    return orchestrator


def _complete_transform():
    return SimpleNamespace(
        process_pending=lambda **kwargs: {
            "completed": True,
            "stop_reason": "complete",
        }
    )


def test_build_routes_exclude_unapproved_historical_sources():
    orchestrator = _bare_hardened(_runtime_config(candidate=True))
    captured_routes = []
    orchestrator.transform_pipeline = _complete_transform()
    orchestrator.build_pipeline = SimpleNamespace(
        run=lambda route: captured_routes.append(route) or []
    )

    summary = asyncio.run(
        orchestrator._run_hardened(
            timeout=10,
            no_publish=True,
            allow_partial_export=False,
        )
    )

    assert summary["status"] == "completed"
    assert summary["approved_sources"] == 1
    assert summary["excluded_sources"] == 1
    assert captured_routes[0]["from_sources"] == ["approved"]


def test_optional_destination_policy_reaches_publisher():
    config = _runtime_config()
    config.publishing.routes[0].destinations[0].required = False
    orchestrator = _bare_hardened(config)
    captured_destinations = []
    orchestrator.transform_pipeline = _complete_transform()
    orchestrator.build_pipeline = SimpleNamespace(
        run=lambda route: [
            {
                "route_name": route["name"],
                "artifact_hash": "a" * 64,
                "format": "npvt",
                "data": b"payload",
            }
        ]
    )
    orchestrator.publish_pipeline = SimpleNamespace(
        run=lambda result, destinations: captured_destinations.extend(destinations)
    )

    summary = asyncio.run(
        orchestrator._run_hardened(
            timeout=10,
            no_publish=False,
            allow_partial_export=False,
        )
    )

    assert summary["status"] == "completed"
    assert captured_destinations
    assert captured_destinations[0]["required"] is False


def test_transform_deadline_stops_build_and_marks_timeout():
    orchestrator = _bare_hardened(_runtime_config())
    deadlines = []
    build_called = False

    def transform(**kwargs):
        deadlines.append(kwargs.get("deadline_monotonic"))
        return {"completed": False, "stop_reason": "deadline"}

    def build(route):
        nonlocal build_called
        build_called = True
        return []

    orchestrator.transform_pipeline = SimpleNamespace(process_pending=transform)
    orchestrator.build_pipeline = SimpleNamespace(run=build)

    summary = asyncio.run(
        orchestrator._run_hardened(
            timeout=10,
            no_publish=True,
            allow_partial_export=False,
        )
    )

    assert deadlines and deadlines[0] is not None
    assert summary["status"] == "timed_out"
    assert summary["timed_out_stage"] == "transformation"
    assert summary["transform_completed"] is False
    assert build_called is False


def test_validate_config_rejects_unsafe_and_duplicate_route_identities():
    base = _runtime_config()
    bad_name = base.model_copy(deep=True)
    bad_name.publishing.routes[0].name = "unsafe/route"
    with pytest.raises(ValueError, match="filesystem-safe"):
        validate_config(bad_name)

    duplicate = base.model_copy(deep=True)
    duplicate.publishing.routes.append(duplicate.publishing.routes[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="Duplicate route name"):
        validate_config(duplicate)


def test_validate_config_rejects_ambiguous_route_prefixes():
    config = _runtime_config()
    second = config.publishing.routes[0].model_copy(deep=True)
    config.publishing.routes[0].name = "prod"
    second.name = "production"
    config.publishing.routes.append(second)

    with pytest.raises(ValueError, match="ambiguous output prefixes"):
        validate_config(config)


def test_validate_config_rejects_duplicate_route_members():
    config = _runtime_config()
    route = config.publishing.routes[0]
    route.from_sources.append("approved")
    with pytest.raises(ValueError, match="duplicate source references"):
        validate_config(config)

    config = _runtime_config()
    route = config.publishing.routes[0]
    route.formats.append("npvt")
    with pytest.raises(ValueError, match="duplicate formats"):
        validate_config(config)

    config = _runtime_config()
    route = config.publishing.routes[0]
    route.destinations.append(route.destinations[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="duplicate destination identity"):
        validate_config(config)


def test_production_runtime_factory_installs_governed_build(monkeypatch):
    marker = object()
    fake_orchestrator = SimpleNamespace(
        repo=object(),
        artifact_store=object(),
        registry=object(),
        build_pipeline=None,
    )
    constructed = {}

    def fake_orchestrator_factory(config, *, max_workers, fetch_windows):
        constructed["max_workers"] = max_workers
        constructed["fetch_windows"] = fetch_windows
        return fake_orchestrator

    def fake_governed(repo, artifact_store, registry, route_policies):
        constructed["route_policies"] = route_policies
        return marker

    monkeypatch.setattr(
        runtime_factory,
        "OptimizedHardenedOrchestrator",
        fake_orchestrator_factory,
    )
    monkeypatch.setattr(
        runtime_factory,
        "reconcile_configured_bot_consumers",
        lambda repo, config: {"ok": True},
    )
    monkeypatch.setattr(runtime_factory, "GovernedBuildPipeline", fake_governed)

    config = _runtime_config()
    result = runtime_factory.create_production_orchestrator(
        config,
        max_workers=7,
        fetch_windows={"file_fresh_hours": 5},
    )

    assert result is fake_orchestrator
    assert result.build_pipeline is marker
    assert constructed["max_workers"] == 7
    assert constructed["fetch_windows"] == {"file_fresh_hours": 5}
    assert constructed["route_policies"] == {
        "route": ("compatible", False),
    }
