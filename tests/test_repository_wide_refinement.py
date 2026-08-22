from __future__ import annotations

import inspect
import math
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from huntx.cli import main as cli_main
from huntx.cli.commands import run as compatibility_run
from huntx.cli.run_service import (
    _configured_session_identities,
    _normalize_fetch_windows,
    _process_session_lock_path,
    _resolve_run_timeout,
    execute_pipeline_run,
)
from huntx.core.geo_routing import GeoRoutingEngine
from huntx.core.scoring import ProxyScoringEngine
from huntx.core.self_healing import SelfHealingDaemon
from huntx.core.session_lease import session_lease_path


def _source(session: str | None, *, source_type: str = "telegram_user"):
    telegram_user = SimpleNamespace(session=session) if source_type == "telegram_user" else None
    return SimpleNamespace(type=source_type, telegram_user=telegram_user)


def test_all_cli_run_entrypoints_use_shared_governed_service():
    main_source = inspect.getsource(cli_main._cmd_run)
    compatibility_source = inspect.getsource(compatibility_run.run_command)

    assert "execute_pipeline_run" in main_source
    assert "execute_pipeline_run" in compatibility_source
    assert "Orchestrator(" not in main_source
    assert "Orchestrator(" not in compatibility_source


def test_configured_session_identities_are_complete_deduplicated_and_sorted():
    config = SimpleNamespace(
        sources=[
            _source("beta"),
            _source("alpha"),
            _source("beta"),
            _source(None),
            _source("ignored", source_type="telegram"),
        ]
    )
    assert _configured_session_identities(config) == ("alpha", "beta")


def test_process_session_lock_never_aliases_durable_session_lease(tmp_path):
    process_lock = _process_session_lock_path(tmp_path, "secret-session")
    durable_lease = session_lease_path(tmp_path, "secret-session")

    assert process_lock != durable_lease
    assert process_lock.parent.name == "process-locks"
    assert durable_lease.parent.name == "session-leases"


def test_run_service_fences_process_and_every_configured_session(tmp_path):
    config = SimpleNamespace(sources=[_source("beta"), _source("alpha")])
    orchestrator = MagicMock()
    orchestrator.run.return_value = {
        "status": "completed",
        "total_artifacts": 1,
        "ingest_ok": 2,
    }

    with (
        patch("huntx.cli.run_service.load_config", return_value=config),
        patch("huntx.cli.run_service.validate_config"),
        patch(
            "huntx.cli.run_service.create_production_orchestrator",
            return_value=orchestrator,
        ) as factory,
        patch("huntx.cli.run_service._session_lock_root", return_value=tmp_path),
        patch(
            "huntx.cli.run_service.acquire_lock",
            side_effect=lambda _path: nullcontext(),
        ) as lock,
        patch("huntx.cli.run_service.paths.STATE_DIR", tmp_path),
        patch("huntx.cli.run_service.emit_run_health"),
    ):
        execution = execute_pipeline_run(
            "config.yaml",
            max_workers=4,
            timeout=30,
            allow_partial_export=False,
        )

    assert execution.health.disposition == "success"
    factory.assert_called_once_with(config, max_workers=4, fetch_windows=None)
    assert lock.call_args_list == [
        call(tmp_path / "huntx.lock"),
        call(_process_session_lock_path(tmp_path, "alpha")),
        call(_process_session_lock_path(tmp_path, "beta")),
    ]
    orchestrator.run.assert_called_once_with(
        timeout=30.0,
        no_publish=False,
        allow_partial_export=False,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, -0.01])
def test_fetch_windows_reject_nonfinite_or_negative_values(value):
    with pytest.raises(ValueError):
        _normalize_fetch_windows({"msg_fresh_hours": value})


def test_fetch_windows_reject_unknown_keys():
    with pytest.raises(ValueError, match="Unknown fetch-window"):
        _normalize_fetch_windows({"not_a_real_window": 1})


def test_invalid_timeout_environment_falls_back(monkeypatch):
    monkeypatch.setenv("HUNTX_RUN_TIMEOUT", "nan")
    assert _resolve_run_timeout() == 12600.0


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), "oops"])
def test_explicit_invalid_timeout_is_rejected(value):
    with pytest.raises(ValueError):
        _resolve_run_timeout(value)


def test_self_healing_rejects_invalid_backoff_schedules():
    for schedule in ([], [0], [-1], [True]):
        with pytest.raises(ValueError):
            SelfHealingDaemon(backoff_schedule=schedule)


def test_self_healing_nonpositive_purge_is_fail_safe_noop():
    daemon = SelfHealingDaemon(backoff_schedule=[10])
    daemon.record_failure("hash", "vless://user@example.com:443", current_time=100.0)
    assert daemon.purge_stale_proxies(max_age_hours=0, current_time=1000.0) == 0
    assert len(daemon.get_due_for_retest(current_time=1000.0)) == 1
    daemon.close()


def test_self_healing_rejects_nonfinite_time():
    daemon = SelfHealingDaemon()
    with pytest.raises(ValueError):
        daemon.record_failure("hash", "vless://user@example.com:443", current_time=math.nan)
    daemon.close()


def test_proxy_scoring_is_bounded_for_malformed_metrics():
    engine = ProxyScoringEngine()
    cases = [
        {"latency_ms": float("nan"), "historical_success_rate": float("nan")},
        {"latency_ms": -100, "historical_success_rate": 5},
        {"latency_ms": "oops", "historical_success_rate": None},
        {"latency_ms": True, "historical_success_rate": False},
    ]
    for record in cases:
        score = engine.score_proxy(record)
        assert math.isfinite(score)
        assert 0.0 <= score <= 100.0


def test_geo_routing_handles_ipv6_malformed_bytes_and_invalid_filter_inputs():
    engine = GeoRoutingEngine()
    assert engine.infer_country_code("vless://u@[2001:db8::1]:443#DE") == "DE"
    assert engine.infer_country_code(None) == "XX"  # type: ignore[arg-type]
    assert engine.normalize_protocol(None) == "unknown"

    classified = engine.classify_proxy({"data": b"\xff\xfe", "protocol": None})
    assert classified["country_code"] == "XX"
    assert classified["protocol"] == "unknown"
    assert engine.route_by_region([classified], "ZZ") == []
    assert engine.route_by_protocol([classified], "not-a-protocol") == []
