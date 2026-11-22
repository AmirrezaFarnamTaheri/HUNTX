"""Authenticated HTTPS sweeps must remain fresh, bounded and fair.

The production regression had 86k candidates per format, a 30-minute sweep,
186 genuine successes, and ZERO admissions because each success expired before
the sweep ended. Preserve five-minute proof TTL and fail-closed behavior.
"""
from __future__ import annotations

import threading
import time

from huntx.core import proxy_health as health


def _record(index: int, *, historical: bool = False) -> dict:
    item = {
        "data": {
            "line": f"trojan://synthetic-{index}@edge.example.org:443?security=tls"
        }
    }
    if historical:
        item["historical_retest"] = True
    return item


def _isolate_network(monkeypatch) -> None:
    monkeypatch.setattr(health.shutil, "which", lambda _: "/synthetic/sing-box")
    monkeypatch.setattr(health, "_verify_engine", lambda _: None)


def test_health_sweep_budget_cannot_age_out_first_success(monkeypatch):
    # A configurable 30-minute sweep outlived the required 300-second proof.
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "1800")
    assert 1 <= health._sweep_budget_seconds() <= 240
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "2400")
    assert health._sweep_budget_seconds() <= 240


def test_recent_sweep_rotates_every_candidate_without_starvation():
    keys = [f"identity-{number}" for number in range(29)]
    bucket_orders = [health._probe_order(keys, set(), slot) for slot in range(len(keys))]
    assert {order[0] for order in bucket_orders} == set(keys)
    for order in bucket_orders:
        assert len(order) == len(keys)
        assert len(set(order)) == len(keys)
    # Source-independent historical successes keep the reserved first slots.
    with_history = health._probe_order(keys, {"identity-14", "identity-28"}, 99)
    assert with_history[:2] == ["identity-14", "identity-28"]


def test_sweep_never_queues_entire_restored_proxy_inventory(monkeypatch):
    _isolate_network(monkeypatch)
    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "2")
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "1")
    original_executor = health.concurrent.futures.ThreadPoolExecutor
    counter = {"submitted": 0}
    started = threading.Event()
    release = threading.Event()
    finished: dict[str, object] = {}

    class CountingExecutor(original_executor):
        def submit(self, *args, **kwargs):
            counter["submitted"] += 1
            return super().submit(*args, **kwargs)

    def blocked_probe(_uri: str, _binary: str, *, timeout: float) -> dict:
        started.set()
        release.wait(timeout=2)
        return {"ok": False, "reason": "https_path_failed"}

    monkeypatch.setattr(health.concurrent.futures, "ThreadPoolExecutor", CountingExecutor)
    monkeypatch.setattr(health, "check_proxy", blocked_probe)

    def run_gate():
        try:
            finished["result"] = health.verified_records([_record(i) for i in range(80)])
        except Exception as exc:
            finished["error"] = exc

    thread = threading.Thread(target=run_gate, daemon=True)
    thread.start()
    try:
        assert started.wait(timeout=2)
        time.sleep(0.12)
        # At most two small waves, never one future per historical candidate.
        assert counter["submitted"] <= 4, counter
    finally:
        release.set()
        thread.join(timeout=4)
    assert not thread.is_alive()
    assert "error" not in finished, finished.get("error")
    result = finished["result"]
    assert result == []
    report = result.gate_report
    assert report["candidates"] == 80
    assert report["admitted"] == 0
    assert sum(report["reasons"].values()) == 80


def test_historical_retest_is_probed_before_unverified_recent_tail(monkeypatch):
    _isolate_network(monkeypatch)
    monkeypatch.setenv("HUNTX_HEALTH_WORKERS", "1")
    monkeypatch.setenv("HUNTX_HEALTH_BUDGET", "1")
    recorded: list[str] = []

    def failed_check(uri: str, _binary: str, *, timeout: float) -> dict:
        recorded.append(uri)
        return {"ok": False, "reason": "https_path_failed"}

    monkeypatch.setattr(health, "check_proxy", failed_check)
    records = [_record(i) for i in range(50)]
    records.append(_record(999, historical=True))
    result = health.verified_records(records)
    assert recorded
    assert recorded[0] == records[-1]["data"]["line"]
    assert result.gate_report["candidates"] == len(records)
    assert sum(result.gate_report["reasons"].values()) == len(records)
