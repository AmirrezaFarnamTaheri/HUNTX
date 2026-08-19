import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from huntx.bot.constants import (
    _BOT_ADMIN_COMMANDS,
    _BOT_APPROVED_COMMANDS,
    _BOT_COMMANDS,
    _BOT_PUBLIC_COMMANDS,
)
from huntx.bot.interactive import InteractiveBot
from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishingConfig,
    PublishRoute,
    SourceConfig,
    SourceSelector,
    TelegramSourceConfig,
)
from huntx.config.validate import validate_config
from huntx.core.output_ownership import OUTPUT_OWNERSHIP_MANIFEST, export_owned_outputs
from huntx.state.db import open_db
from huntx.state.ingestion_queue import PersistentIngestionQueue
from huntx.state.repo import StateRepo


class _Event:
    def __init__(self, sender_id=1, chat_id=1, *, is_private=True):
        self.sender_id = sender_id
        self.chat_id = chat_id
        self.is_private = is_private
        self.data = None
        self.responses = []

    async def respond(self, message, **kwargs):
        self.responses.append(str(message))


def _bot(tmp_path, monkeypatch):
    monkeypatch.delenv("HUNTX_ADMINS", raising=False)
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "bot.db")
    bot.repo = StateRepo(bot.db)
    return bot


def _config_with_route(name: str) -> AppConfig:
    return AppConfig(
        sources=[
            SourceConfig(
                id="source",
                type="telegram",
                selector=SourceSelector(include_formats=["all"]),
                telegram=TelegramSourceConfig(token="123:source", chat_id="-1001"),
            )
        ],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name=name,
                    from_sources=["source"],
                    formats=["npvt"],
                    destinations=[DestinationConfig(chat_id="-1002", token="123:publish")],
                )
            ]
        ),
    )


def test_ci_quality_toolchain_is_single_version_pinned_source():
    lock = Path("requirements-ci.txt").read_text(encoding="utf-8")
    requirements = [
        line.strip()
        for line in lock.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert requirements
    assert all("==" in requirement for requirement in requirements)

    pr_workflow = Path(".github/workflows/pr-validation.yml").read_text(encoding="utf-8")
    prod_workflow = Path(".github/workflows/huntx.yml").read_text(encoding="utf-8")
    for workflow in (pr_workflow, prod_workflow):
        assert "-r requirements-ci.txt" in workflow
        assert "pip install --prefer-binary flake8 mypy" not in workflow


def test_bot_command_policy_is_exhaustive_disjoint_and_hides_admin_menu():
    declared = _BOT_PUBLIC_COMMANDS | _BOT_APPROVED_COMMANDS | _BOT_ADMIN_COMMANDS
    assert not (_BOT_PUBLIC_COMMANDS & _BOT_APPROVED_COMMANDS)
    assert not (_BOT_PUBLIC_COMMANDS & _BOT_ADMIN_COMMANDS)
    assert not (_BOT_APPROVED_COMMANDS & _BOT_ADMIN_COMMANDS)

    menu_names = {command.command for command in _BOT_COMMANDS}
    assert menu_names <= declared
    assert "status" in _BOT_ADMIN_COMMANDS
    assert "status" not in menu_names


def test_bot_access_policy_distinguishes_pending_approved_admin_and_group(tmp_path, monkeypatch):
    bot = _bot(tmp_path, monkeypatch)
    bot._register_user("1", "1", "alice")

    assert asyncio.run(bot._require_named_access(_Event(), "protocols")) is True

    pending = _Event()
    assert asyncio.run(bot._require_named_access(pending, "count")) is False
    assert any("Approval required" in response for response in pending.responses)

    with bot.db.connect() as conn:
        conn.execute("UPDATE bot_users SET approved = 1 WHERE user_id = '1'")
    assert asyncio.run(bot._require_named_access(_Event(), "count")) is True

    non_admin = _Event()
    assert asyncio.run(bot._require_named_access(non_admin, "status")) is False
    assert any("Access Denied" in response for response in non_admin.responses)

    monkeypatch.setenv("HUNTX_ADMINS", "1")
    assert asyncio.run(bot._require_named_access(_Event(), "status")) is True

    group = _Event(chat_id=-1001, is_private=False)
    assert asyncio.run(bot._require_named_access(group, "protocols")) is False
    assert any("Private chat required" in response for response in group.responses)


def test_prefix_related_route_names_are_valid_with_exact_filename_ownership():
    config = _config_with_route("prod")
    second = config.publishing.routes[0].model_copy(deep=True)
    second.name = "production"
    config.publishing.routes.append(second)
    validate_config(config)


def test_structural_output_manifest_never_prunes_unowned_prefix_files(tmp_path):
    output_dir = tmp_path / "outputs"
    config = SimpleNamespace(
        routes=[
            SimpleNamespace(name="prod", formats=["npvt"]),
            SimpleNamespace(name="production", formats=["npvt"]),
        ]
    )
    orchestrator = SimpleNamespace(
        paths=SimpleNamespace(output_dir=output_dir),
        config=config,
        _output_retention_days=lambda: 0,
    )

    export_owned_outputs(
        orchestrator,
        [
            {"route_name": "prod", "format": "npvt", "data": b"prod"},
            {"route_name": "production", "format": "npvt", "data": b"production"},
        ],
    )
    unrelated = output_dir / "production_notes.txt"
    unrelated.write_text("operator notes", encoding="utf-8")
    stale = output_dir / "production.npvt"
    os.utime(stale, (1, 1))

    export_owned_outputs(
        orchestrator,
        [{"route_name": "prod", "format": "npvt", "data": b"prod-v2"}],
    )

    assert (output_dir / "prod.npvt").read_bytes() == b"prod-v2"
    assert not stale.exists()
    assert unrelated.read_text(encoding="utf-8") == "operator notes"

    manifest = json.loads((output_dir / OUTPUT_OWNERSHIP_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["files"] == {"prod.npvt": {"format": "npvt", "route": "prod"}}


def test_source_revocation_invalidates_active_lease_and_rolls_back_page_transaction(tmp_path):
    db = open_db(tmp_path / "queue.db")
    queue = PersistentIngestionQueue(db)
    source = SimpleNamespace(id="source", type="telegram_user")
    queue.seed_rolling_horizon(
        [source],
        now=7200,
        lookback_seconds=3600,
        window_seconds=3600,
    )
    item = queue.claim_next("worker", lease_seconds=300, now=7200)
    assert item is not None

    assert queue.terminalize_source("source", "trust revoked", now=7201) == 1
    assert queue.summary()["remaining"] == 0

    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, lease_owner, lease_token FROM ingestion_work_items WHERE id = ?",
            (item.id,),
        ).fetchone()
        assert row["status"] == "quarantined"
        assert row["lease_owner"] is None
        assert row["lease_token"] is None
        conn.execute("CREATE TABLE page_probe (value TEXT NOT NULL)")

    with pytest.raises(RuntimeError, match="lease was lost"):
        with db.connect() as conn:
            conn.execute("INSERT INTO page_probe(value) VALUES ('must-rollback')")
            queue.checkpoint_page(
                item.id,
                "worker",
                lease_token=item.lease_token,
                continuation_cursor=None,
                items_ingested=1,
                bytes_ingested=1,
                completed=True,
                conn=conn,
                now=7202,
            )

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS c FROM page_probe").fetchone()["c"] == 0


def test_huntx_engine_is_part_of_root_go_module():
    assert not Path("cmd/huntx-engine/go.mod").exists()
    root_mod = Path("go.mod").read_text(encoding="utf-8")
    assert "module github.com/AmirrezaFarnamTaheri/HUNTX" in root_mod

    engine_main = Path("cmd/huntx-engine/main.go").read_text(encoding="utf-8")
    assert '"huntx-engine/' not in engine_main
    assert '"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/' in engine_main

    pr_workflow = Path(".github/workflows/pr-validation.yml").read_text(encoding="utf-8")
    assert "cmd/huntx-engine/go.mod" not in pr_workflow
    assert "go build ./cmd/huntx-engine" in pr_workflow
