"""Regression coverage for PR #76 review findings and follow-up defects."""

import hashlib
import io
import zipfile

import pytest

from huntx.bot.interactive import InteractiveBot
from huntx.config.schema import AppConfig, PublishRoute, PublishingConfig, SourceConfig
from huntx.config.validate import validate_config
from huntx.connectors.v2ray_collector.connector import (
    V2RayCollectorConnector,
    V2RayCollectorItem,
)
from huntx.formats.nm import NmHandler
from huntx.formats.registry import FormatRegistry
from huntx.pipeline.ingest import IngestionPipeline
from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.store.raw_store import RawStore


class _FakeClient:
    def __init__(self):
        self.callbacks = []

    def add_event_handler(self, callback, event):
        self.callbacks.append(callback.__name__)


class _FakeEvent:
    def __init__(self, sender_id, text):
        self.sender_id = sender_id
        self.chat_id = sender_id
        self.is_private = True
        self.data = None
        self.text = text
        self.responses = []

    async def respond(self, message, **kwargs):
        self.responses.append(message)
        return None


def test_approval_commands_are_registered_through_private_admin_policy():
    bot = object.__new__(InteractiveBot)
    bot.client = _FakeClient()

    bot._register_handlers()

    assert "_private_approve" in bot.client.callbacks
    assert "_private_deny" in bot.client.callbacks
    assert "_private_pending" in bot.client.callbacks
    assert "_on_approve" not in bot.client.callbacks
    assert "_on_deny" not in bot.client.callbacks
    assert "_on_pending" not in bot.client.callbacks


@pytest.mark.asyncio
async def test_approval_commands_change_real_delivery_selector(tmp_path, monkeypatch):
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    monkeypatch.setenv("HUNTX_ADMINS", "9001")

    with bot.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
            VALUES ('12345', '12345', 1.0, 0, 0)
            """
        )

    approve = _FakeEvent(9001, "/approve 12345")
    await bot._on_approve(approve)
    assert [row["user_id"] for row in bot._get_active_users()] == ["12345"]

    deny = _FakeEvent(9001, "/deny 12345")
    await bot._on_deny(deny)
    assert bot._get_active_users() == []

    pending = _FakeEvent(9001, "/pending")
    await bot._on_pending(pending)
    assert pending.responses
    assert "12345" in pending.responses[-1]


@pytest.mark.asyncio
async def test_approval_commands_reject_non_admin(tmp_path, monkeypatch):
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    monkeypatch.setenv("HUNTX_ADMINS", "9001")

    event = _FakeEvent(42, "/approve 12345")
    await bot._on_approve(event)

    assert event.responses
    assert "Access Denied" in event.responses[-1]


def test_v2ray_external_id_is_full_hash_and_order_independent():
    line = "vless://user@example.com:443?type=tcp"
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()

    assert V2RayCollectorConnector.build_external_id(line) == f"goscrap_{digest}"
    assert len(V2RayCollectorConnector.build_external_id(line).split("_", 1)[1]) == 64


def test_v2ray_legacy_external_id_is_not_reingested(tmp_path):
    data = b"vless://user@example.com:443?type=tcp"
    digest = hashlib.sha256(data).hexdigest()
    legacy_external_id = f"goscrap_{digest[:16]}_37"

    db = open_db(tmp_path / "state.db")
    repo = StateRepo(db)
    raw_store = RawStore(tmp_path / "raw")
    pipeline = IngestionPipeline(raw_store, repo)

    repo.record_file(
        "v2ray",
        legacy_external_id,
        digest,
        len(data),
        "collected_configs.txt",
        status="processed",
    )

    item = V2RayCollectorItem(
        external_id=f"goscrap_{digest}",
        data=data,
        metadata={
            "filename": "collected_configs.txt",
            "is_text": True,
            "dedupe_by_content": True,
        },
    )

    processed, _, skipped, _, _ = pipeline._process_batch("v2ray", [item])

    assert processed == 0
    assert skipped == 1
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT external_id FROM seen_files WHERE source_id = 'v2ray'"
        ).fetchall()
    assert [row["external_id"] for row in rows] == [legacy_external_id]


def test_v2ray_duplicate_content_is_suppressed_within_batch(tmp_path):
    data = b"trojan://secret@example.com:443"
    digest = hashlib.sha256(data).hexdigest()
    item_a = V2RayCollectorItem(
        f"goscrap_{digest}",
        data,
        {"filename": "collected_configs.txt", "dedupe_by_content": True},
    )
    item_b = V2RayCollectorItem(
        f"goscrap_{digest}",
        data,
        {"filename": "collected_configs.txt", "dedupe_by_content": True},
    )

    db = open_db(tmp_path / "state.db")
    pipeline = IngestionPipeline(RawStore(tmp_path / "raw"), StateRepo(db))
    processed, _, skipped, _, _ = pipeline._process_batch("v2ray", [item_a, item_b])

    assert processed == 1
    assert skipped == 1


def test_nm_is_buildable_as_opaque_archive_without_decryption_secret(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("HUNTX_NETMOD_KEY", raising=False)
    raw_store = RawStore(tmp_path / "raw")
    handler = NmHandler(raw_store)
    raw_data = b"opaque-encrypted-netmod-fixture"
    raw_hash = raw_store.save(raw_data)

    records = handler.parse(raw_data, {"filename": "fixture.nm"})

    assert len(records) == 1
    assert records[0]["data"]["blob_hash"] == raw_hash
    assert "decrypted" not in records[0]["data"]

    artifact = handler.build(records)
    with zipfile.ZipFile(io.BytesIO(artifact), "r") as archive:
        assert archive.namelist() == ["fixture.nm"]
        assert archive.read("fixture.nm") == raw_data


def test_registry_preserves_api_and_reports_nm_builder(tmp_path):
    registry = FormatRegistry()
    registry.register(NmHandler(RawStore(tmp_path / "raw")))

    assert registry.get("nm") is not None
    assert "nm" in registry.list_formats()
    assert registry.can_build("nm") is True


def test_validate_config_accepts_real_nm_output_route(tmp_path, monkeypatch):
    registry = FormatRegistry()
    registry.register(NmHandler(RawStore(tmp_path / "raw")))
    monkeypatch.setattr(FormatRegistry, "_shared_instance", registry)

    config = AppConfig(
        sources=[SourceConfig(id="collector", type="v2ray_collector")],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="nm-output",
                    from_sources=["collector"],
                    formats=["nm"],
                    destinations=[],
                )
            ]
        ),
    )

    validate_config(config)


def test_validate_config_accepts_v2ray_collector_source(monkeypatch):
    registry = FormatRegistry()
    monkeypatch.setattr(FormatRegistry, "_shared_instance", registry)

    config = AppConfig(
        sources=[SourceConfig(id="collector", type="v2ray_collector")],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name="collector-output",
                    from_sources=["collector"],
                    formats=["npvt"],
                    destinations=[],
                )
            ]
        ),
    )

    validate_config(config)
