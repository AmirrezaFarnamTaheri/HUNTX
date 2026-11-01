"""High-recall caps must enable slow authenticated proxies without hiding failure.

All limits remain finite and publisher evidence retains the same 300s TTL.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time

from huntx.core import proxy_health as health
from huntx.pipeline import transform


URI = "trojan://secret@5.5.5.5:443?security=tls"


def test_larger_sweep_can_use_48_workers_and_verify_slow_18_second_path(monkeypatch):
    requested = []
    engine = concurrent.futures.ThreadPoolExecutor

    def tracking_pool(*args, **kwargs):
        requested.append(kwargs.get("max_workers"))
        return engine(*args, **kwargs)

    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "48")
    monkeypatch.setenv("HUNTX_HEALTH_TIMEOUT", "25")
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "1500")
    monkeypatch.setattr(health.shutil, "which", lambda _: "/fake/sing-box")
    monkeypatch.setattr(health, "_verify_engine", lambda _: None)
    monkeypatch.setattr(health.concurrent.futures, "ThreadPoolExecutor", tracking_pool)
    monkeypatch.setattr(health, "check_proxy", lambda *_a, **_k: {
        "ok": True, "checked_at": time.time(),
        "latency_ms": 18500, "reason": "authenticated_https",
    })

    checked = health.verified_records([{"data": {"line": URI}}])
    assert requested == [48]
    assert len(checked) == 1
    assert checked[0]["data"]["latency_ms"] == 18500
    assert checked[0]["data"]["probe_expires_at"] - checked[0]["data"]["probe_checked_at"] == 300


def test_budget_exhaustion_does_not_wait_for_running_or_queued_probes(monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    def slow_checker(*_args, **_kw):
        entered.set()
        release.wait(timeout=3)
        return {"ok": False, "reason": "https_path_failed"}

    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "1")
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "1")
    monkeypatch.setattr(health.shutil, "which", lambda _: "/fake/sing-box")
    monkeypatch.setattr(health, "_verify_engine", lambda _: None)
    monkeypatch.setattr(health, "check_proxy", slow_checker)
    started = time.monotonic()
    try:
        result = health.verified_records([{"data": {"line": URI}}])
        elapsed = time.monotonic() - started
        assert entered.is_set()
        assert elapsed < 2.3, f"health budget 1s blocked for {elapsed:.2f}s"
        assert result == []
        assert result.gate_report["admitted"] == 0
        assert result.gate_report["identities"]
        assert "slow_checker" not in str(result.gate_report)
    finally:
        release.set()


def test_transform_defaults_cover_more_approved_work_without_truncating_files():
    assert transform._DEFAULT_MAX_RECORDS >= 2_000_000
    assert transform._DEFAULT_MAX_BATCHES >= 2_500
    # Per-file chunks must remain small to avoid OOM; this is NOT an
    # observation-dropping quota, only the SQL write batch size.
    assert transform._DEFAULT_MAX_RECORDS_PER_FILE <= 20_000


def test_invalid_health_limits_stay_bounded(monkeypatch):
    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "1000000")
    monkeypatch.setenv("HUNTX_HEALTH_TIMEOUT", "Infinity")
    assert health._bounded("HUNTX_HEALTH_WORKERS", 24, 1, 64) == 64
    assert health._bounded("HUNTX_HEALTH_TIMEOUT", 25, 1, 30) == 25
