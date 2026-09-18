"""Offline diagnostics for the checked-in production configuration.

AppConfig has no telemetry section. Its health-related controls are source
trust and route probe-freshness policy; loader logging is checked separately.
No connector, real publisher, or persistent state repository is instantiated.
"""

import datetime
import hashlib
import logging
from pathlib import Path
import re
import socket
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from huntx.config.loader import load_config
from huntx.config.schema import (
    DestinationConfig,
    PublicationTier,
    PublishRoute,
    SourceTrustState,
)
from huntx.config.validate import _is_derived_output_format, validate_config
from huntx.formats.register_builtin import register_all_formats
from huntx.formats.registry import FormatRegistry
from huntx.pipeline import publish
from huntx.state.repo import StateRepo
from huntx.store.raw_store import RawStore


PROD_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "config.prod.yaml"
DUMMY_ENV = {
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "offline-dummy-hash",
    "TELEGRAM_USER_SESSION": "offline-dummy-session",
    "TELEGRAM_TOKEN": "12345:offline-ingest-token",
    "PUBLISH_BOT_TOKEN": "67890:offline-publish-token",
}


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Config diagnostics must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    # Fail before expansion if new placeholders lack safe test replacements.
    placeholders = set(re.findall(r"\$\{([A-Za-z0-9_]+)", PROD_CONFIG.read_text(encoding="utf-8")))
    assert placeholders <= DUMMY_ENV.keys(), "Add dummy values for new config placeholders"
    for name, value in DUMMY_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("HUNTX_STRICT", "1")
    monkeypatch.setenv("CI", "0")


@pytest.fixture
def registry(monkeypatch, tmp_path):
    registry = FormatRegistry()
    register_all_formats(registry, RawStore(tmp_path / "raw"))
    # Avoid validator fallback constructing RawStore at its production path;
    # monkeypatch restores any prior singleton after each test.
    monkeypatch.setattr(FormatRegistry, "_shared_instance", registry)
    return registry


@pytest.fixture
def prod_config():
    return load_config(PROD_CONFIG)


def test_production_config_loads_and_validates_strictly(prod_config, registry):
    assert prod_config.sources
    assert prod_config.routes
    for source in prod_config.sources:
        assert source.telegram_user is not None
        assert type(source.telegram_user.api_id) is int
        assert source.telegram_user.api_id == 12345
        assert source.telegram_user.api_hash == DUMMY_ENV["TELEGRAM_API_HASH"]
        assert source.telegram_user.session == DUMMY_ENV["TELEGRAM_USER_SESSION"]
    validate_config(prod_config)


def test_loader_reports_counts_without_credentials(caplog):
    with caplog.at_level(logging.INFO, logger="huntx.config.loader"):
        config = load_config(PROD_CONFIG)
    messages = [record.getMessage() for record in caplog.records if record.name == "huntx.config.loader"]
    assert f"Loaded config with {len(config.sources)} sources and {len(config.routes)} routes." in messages
    for value in DUMMY_ENV.values():
        assert value not in caplog.text


@pytest.mark.parametrize("name", ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_USER_SESSION"])
def test_missing_required_placeholder_is_diagnosed(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(ValueError, match=f"Missing required environment variable: {name}"):
        load_config(PROD_CONFIG)


def test_noninteger_api_id_is_diagnosed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "offline-not-an-integer")
    with pytest.raises(ValidationError, match="api_id.*must be an integer"):
        load_config(PROD_CONFIG)


def test_routes_cover_sources_without_duplicate_references(prod_config):
    source_ids = [source.id for source in prod_config.sources]
    assert len(source_ids) == len(set(source_ids))
    route_names = [route.name for route in prod_config.routes]
    assert len(route_names) == len(set(route_names))
    for route in prod_config.routes:
        assert route.from_sources
        assert len(route.from_sources) == len(set(route.from_sources))
        assert set(route.from_sources) <= set(source_ids)
    all_sources = next(route for route in prod_config.routes if route.name == "all_sources")
    assert set(all_sources.from_sources) == set(source_ids)


def test_route_formats_are_registered_buildable_base_formats(prod_config, registry):
    for route in prod_config.routes:
        assert route.formats
        assert len(route.formats) == len(set(route.formats))
        for fmt in route.formats:
            assert not _is_derived_output_format(fmt), (route.name, fmt)
            assert fmt in registry.list_formats(), (route.name, fmt)
            assert registry.can_build(fmt), (route.name, fmt)


def test_destination_identities_are_unique_within_each_route(prod_config):
    # The publisher deduplicates destinations per artifact, not across routes.
    # A route may legitimately have no destinations when publication is
    # disabled for it; only assert the invariant where destinations exist.
    for route in prod_config.routes:
        if not route.destinations:
            continue
        identities = []
        for destination in route.destinations:
            assert destination.mode == "telegram"
            assert destination.chat_id.strip()
            identities.append((destination.mode, destination.chat_id.strip()))
        assert len(identities) == len(set(identities)), route.name


def test_duplicate_destination_is_diagnosed_after_normalization(prod_config, registry):
    # Production publication is currently disabled (destinations: []), so
    # construct a route that carries two destinations to exercise the check.
    route = prod_config.routes[0]
    base = {"chat_id": " 100200300 ", "mode": "telegram",
            "caption_template": "Update: {timestamp}", "token": "t", "required": True}
    route.destinations = [
        DestinationConfig.model_validate(base),
    ]
    duplicate = dict(base)
    duplicate["mode"] = "post_on_change"
    duplicate["chat_id"] = f" {base['chat_id']} "
    route.destinations.append(DestinationConfig.model_validate(duplicate))
    with pytest.raises(ValueError, match="duplicate destination identity"):
        validate_config(prod_config)


def test_configured_captions_render_through_actual_publisher_kwargs(prod_config, monkeypatch):
    class FrozenDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz)

    monkeypatch.setattr(publish.datetime, "datetime", FrozenDateTime)
    publisher = Mock(spec=publish.TelegramPublisher)
    publisher.publish.return_value = "offline-receipt"
    factory = Mock(return_value=publisher)
    monkeypatch.setattr(publish, "TelegramPublisher", factory)
    state = Mock(spec=StateRepo)
    state.ensure_publication_intent.return_value = 1
    state.get_delivery_state.return_value = None
    pipeline = publish.PublishPipeline(state)
    data = b"offline caption fixture; not a real proxy configuration"
    digest = hashlib.sha256(data).hexdigest()
    # Production publication is currently disabled (destinations: []), so
    # attach a synthetic destination to keep exercising the caption contract.
    exercised = False
    for route in prod_config.routes:
        destinations = list(route.destinations)
        if not destinations:
            destinations = [DestinationConfig.model_validate({
                "chat_id": "100200300",
                "mode": "telegram",
                "caption_template": "Update: {timestamp}",
                "token": DUMMY_ENV["PUBLISH_BOT_TOKEN"],
                "required": True,
            })]
        for fmt in route.formats:
            publisher.reset_mock()
            exercised = True
            result = {
                "route_name": route.name,
                "format": fmt,
                "artifact_hash": digest,
                "data": data,
                "count": 7,
            }
            assert pipeline.run(result, [destination.model_dump() for destination in destinations])
            assert publisher.publish.call_count == len(destinations)
            for call, destination in zip(publisher.publish.call_args_list, destinations):
                expected = destination.caption_template.format(
                    timestamp="2026-01-02 03:04:05", sha12=digest[:12], count=7, format=fmt,
                )
                assert expected.strip()
                assert call.args[3] == expected
    assert exercised, "no route formats were exercised"
    factory.assert_called_once_with(DUMMY_ENV["PUBLISH_BOT_TOKEN"])
    state.mark_delivery_failed.assert_not_called()


def test_production_source_health_and_probe_policy(prod_config):
    for source in prod_config.sources:
        assert source.trust_state == SourceTrustState.APPROVED
        assert source.publication_eligible
        if source.discovered_from:
            assert source.approval_evidence
    for route in prod_config.routes:
        expected = route.require_fresh_probe
        if expected is None:
            expected = route.publication_tier == PublicationTier.SECURE
        assert route.effective_require_fresh_probe is expected
        # Publication may be disabled route-wide; only assert the required
        # destination invariant where destinations are configured.
        if route.destinations:
            assert any(destination.required for destination in route.destinations)


@pytest.mark.parametrize("tier", list(PublicationTier))
@pytest.mark.parametrize("override", [None, False, True])
def test_probe_health_policy_defaults_and_explicit_overrides(prod_config, tier, override):
    # Revalidate an in-memory copy; never rewrite the production YAML.
    values = prod_config.routes[0].model_dump()
    values.update(publication_tier=tier, require_fresh_probe=override)
    route = PublishRoute.model_validate(values)
    expected = tier == PublicationTier.SECURE if override is None else override
    assert route.effective_require_fresh_probe is expected
