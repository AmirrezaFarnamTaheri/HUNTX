"""An expired genuine HTTPS success is retest history, not a dead proxy.

A credential-free, identity-checked receipt must retain valid previous
successes for later rescans without adding stale identities to a release.
"""
from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import Mock

import pytest

from huntx.core import proxy_health
from huntx.core.proxy_health import CheckedRecords
from huntx.formats.npvt import NpvtHandler, canonical_proxy_identity
from huntx.pipeline.build import BuildPipeline
from huntx.state.db import open_db
from huntx.state.proxy_lifecycle import record_authenticated_probe, terminalize_proxy
from huntx.state.repo import StateRepo


FRESH = "trojan://fast-credential@198.51.100.2:443?security=tls#fast"
EXPIRED = "trojan://slow-credential@198.51.100.3:443?security=tls#slow"


def digest(uri: str) -> str:
    return hashlib.sha256(canonical_proxy_identity(uri).encode("utf-8")).hexdigest()


def stage(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.sqlite"))
    observation = repo.record_file(
        "approved-source", "message-1", "b" * 64, 130,
        "approved-subscription.txt", status="processed",
    )
    for uri in (FRESH, EXPIRED):
        repo.add_record("b" * 64, "npvt", digest(uri), {"line": uri},
                        source_observation_id=observation)
    with repo.db.connect() as conn:
        conn.execute("UPDATE records SET created_at = '2000-01-01 00:00:00'")
        conn.execute("UPDATE seen_files SET ingested_at = '2000-01-01 00:00:00'")
    return repo, observation


def expired_gate(checked: float):
    return {
        "schema_version": 1,
        "scope": "single_authenticated_https_sweep",
        "candidates": 2, "admitted": 1, "rejected": 1,
        "identities": {
            digest(FRESH): "admitted",
            digest(EXPIRED): "success_expired_before_publication",
        },
        "reasons": {"admitted": 1, "success_expired_before_publication": 1},
        "historical_authenticated_successes": {
            digest(EXPIRED): {
                "checked_at": checked, "expires_at": checked + 300,
                "duration_ms": 18500,
            }
        },
    }


def test_expired_success_keeps_credential_free_proof_in_health_gate(monkeypatch):
    now = time.time()
    seen = 0

    def clock():
        nonlocal seen
        seen += 1
        return now if seen <= 2 else now + 305

    monkeypatch.setattr(proxy_health.shutil, "which", lambda _: "/fake/engine")
    monkeypatch.setattr(proxy_health, "_verify_engine", lambda _: None)
    monkeypatch.setattr(proxy_health, "check_proxy", lambda *_args, **_kw: {
        "ok": True, "checked_at": now, "latency_ms": 18500,
        "reason": "authenticated_https",
    })
    monkeypatch.setattr(proxy_health.time, "time", clock)
    result = proxy_health.verified_records([{"data": {"line": EXPIRED}}])
    assert result == []
    key = digest(EXPIRED)
    assert result.gate_report["identities"][key] == "success_expired_before_publication"
    assert result.gate_report["historical_authenticated_successes"][key] == {
        "checked_at": now, "expires_at": now + 300, "duration_ms": 18500,
    }
    assert "slow-credential" not in json.dumps(result.gate_report)


def test_real_build_persists_expired_success_and_never_adds_it_to_fresh_feed(
    tmp_path, monkeypatch
):
    repo, observation = stage(tmp_path)
    now = time.time()
    accepted = [{"data": {
        "line": FRESH, "probe_kind": "protocol_authenticated",
        "probe_authenticated": True, "probe_checked_at": now - 1,
        "probe_expires_at": now + 299, "latency_ms": 20,
    }}]
    ledger = expired_gate(now - 450)
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setattr(
        "huntx.core.proxy_health.verified_records",
        lambda _rows: CheckedRecords(accepted, ledger),
    )
    registry = Mock()
    registry.get.return_value = NpvtHandler()
    store = Mock()
    store.save_artifact.return_value = "e" * 64
    pipeline = BuildPipeline(repo, store, registry)
    products = pipeline.run({
        "name": "all_sources", "formats": ["npvt"],
        "from_sources": ["approved-source"],
    })
    assert products
    feed = store.save_output.call_args_list[0].args[2].decode("utf-8")
    assert "fast-credential" in feed
    assert "slow-credential" not in feed
    with repo.db.connect() as conn:
        status = {
            row["unique_hash"]: row["authenticated_successes"]
            for row in conn.execute(
                "SELECT unique_hash, authenticated_successes FROM proxy_lifecycle"
            ).fetchall()
        }
    assert status[digest(FRESH)] == 1
    assert status[digest(EXPIRED)] == 1
    repo.prune_old_data(1)
    with repo.db.connect() as conn:
        retained = conn.execute(
            "SELECT COUNT(*) FROM records WHERE source_observation_id = ?",
            (observation,),
        ).fetchone()[0]
    assert retained == 2


def test_unobserved_or_wrong_status_cannot_forge_expired_success(tmp_path):
    repo, _ = stage(tmp_path)
    gate = expired_gate(time.time() - 420)
    key = digest(EXPIRED)
    gate["historical_authenticated_successes"] = {"f" * 64: gate[
        "historical_authenticated_successes"
    ][key]}
    with pytest.raises(ValueError, match="(identity|gate|proof|candidate|mismatch)"):
        repo.persist_expired_authenticated_gate_evidence(
            "npvt", [FRESH, EXPIRED], gate
        )
    with repo.db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM proxy_probe_history"
        ).fetchone()[0] == 0


def test_replayed_expired_proof_is_idempotent_and_cannot_override_newer_failure(
    tmp_path
):
    repo, _ = stage(tmp_path)
    prior = time.time() - 450
    gate = expired_gate(prior)
    assert repo.persist_expired_authenticated_gate_evidence(
        "npvt", [FRESH, EXPIRED], gate
    ) == 1
    assert repo.persist_expired_authenticated_gate_evidence(
        "npvt", [FRESH, EXPIRED], gate
    ) == 0
    record_authenticated_probe(
        repo.db, unique_hash=digest(EXPIRED), record_type="npvt",
        probe_id="newer-negative-vantage", vantage_id="independent-east",
        success=False, checked_at=int(time.time()),
    )
    assert repo.persist_expired_authenticated_gate_evidence(
        "npvt", [FRESH, EXPIRED], gate
    ) == 0
    with repo.db.connect() as conn:
        row = conn.execute(
            "SELECT last_probe_result, authenticated_successes FROM proxy_lifecycle "
            "WHERE unique_hash = ? AND record_type = 'npvt'", (digest(EXPIRED),)
        ).fetchone()
    assert row["last_probe_result"] == "fail"
    assert row["authenticated_successes"] == 1


def test_expired_proof_cannot_revive_explicitly_revoked_proxy(tmp_path):
    repo, _ = stage(tmp_path)
    terminalize_proxy(
        repo.db, unique_hash=digest(EXPIRED), record_type="npvt",
        status="revoked", reason_code="verified_revocation",
    )
    assert repo.persist_expired_authenticated_gate_evidence(
        "npvt", [FRESH, EXPIRED], expired_gate(time.time() - 450)
    ) == 0
    with repo.db.connect() as conn:
        row = conn.execute(
            "SELECT lifecycle_status FROM proxy_lifecycle WHERE unique_hash = ?",
            (digest(EXPIRED),),
        ).fetchone()
    assert row["lifecycle_status"] == "revoked"
