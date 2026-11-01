"""Old genuine HTTPS successes receive bounded, fair source-independent retests.

An old success is *only* a candidate: the publication gate must still obtain a
new certificate-verified HTTPS handshake before the URI can enter the feed.
"""
from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import Mock

import pytest

from huntx.core.proxy_health import CheckedRecords
from huntx.formats.npvt import NpvtHandler, canonical_proxy_identity
from huntx.pipeline.build import BuildPipeline
from huntx.state.db import open_db
from huntx.state.proxy_lifecycle import record_authenticated_probe, terminalize_proxy
from huntx.state.repo import StateRepo


CUTOFF = "2026-10-30 00:00:00"


def _uri(port: int) -> str:
    return f"trojan://history-secret@5.5.5.5:{port}?security=tls#historical"


def _digest(uri: str) -> str:
    return hashlib.sha256(canonical_proxy_identity(uri).encode()).hexdigest()


def _seed(repo: StateRepo, port: int, *, source: str = "approved",
          kind: str = "npvt", old: bool = True, authenticated: bool = True,
          revoked: bool = False, inactive: bool = False) -> str:
    uri = _uri(port)
    fingerprint = hashlib.sha256((uri + source).encode()).hexdigest()
    observation = repo.record_file(
        source, f"message-{port}", fingerprint, 70, "subscription.txt", status="processed",
    )
    repo.add_record(fingerprint, kind, _digest(uri), {"line": uri},
                    source_observation_id=observation)
    with repo.db.connect() as conn:
        conn.execute(
            "UPDATE seen_files SET ingested_at = ? WHERE id = ?",
            ("2000-01-01 00:00:00" if old else "2026-11-01 10:00:00", observation),
        )
        if inactive:
            conn.execute(
                "UPDATE records SET is_active = 0 WHERE source_observation_id = ?",
                (observation,),
            )
    if authenticated:
        record_authenticated_probe(
            repo.db, unique_hash=_digest(uri), record_type=kind,
            probe_id=f"genuine-https-{kind}-{port}", vantage_id="producer-https",
            success=True, checked_at=int(time.time()) - 600,
        )
    if revoked:
        terminalize_proxy(
            repo.db, unique_hash=_digest(uri), record_type=kind,
            reason_code="explicit_revocation", status="revoked",
        )
    return uri


def test_stale_successes_rotate_fairly_without_reentering_fresh_build(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    uris = [_seed(repo, port) for port in range(10000, 10005)]
    assert repo.get_records_for_build(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF
    ) == []

    batches = [
        repo.schedule_historical_retests(
            ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=2,
        )
        for _ in range(3)
    ]
    seen = [{x["data"]["line"] for x in batch} for batch in batches]
    assert [len(batch) for batch in batches] == [2, 2, 2]
    assert not (seen[0] & seen[1])
    assert set(uris) == seen[0] | seen[1] | seen[2]
    assert all(x["historical_retest"] is True for batch in batches for x in batch)
    with repo.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM proxy_probe_history").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM proxy_retest_schedule").fetchone()[0] == 5
    # Scheduling does not mutate the ordinary 72-hour build query.
    assert repo.get_records_for_build(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF
    ) == []


def test_historical_retests_respect_approved_provenance_and_lifecycle(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    due = _seed(repo, 10101)
    _seed(repo, 10102, source="unapproved")
    _seed(repo, 10103, authenticated=False)
    _seed(repo, 10104, revoked=True)
    superseded = _seed(repo, 10105, inactive=True)
    _seed(repo, 10106, old=False)
    _seed(repo, 10107, kind="npvtsub")

    rows = repo.schedule_historical_retests(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=32,
    )
    assert {r["data"]["line"] for r in rows} == {due, superseded}
    assert repo.schedule_historical_retests(
        ["npvt"], ["not-an-approved-source"], min_ingested_at=CUTOFF, limit=32
    ) == []
    assert {r["data"]["line"] for r in repo.schedule_historical_retests(
        ["npvtsub"], ["approved"], min_ingested_at=CUTOFF, limit=32
    )} == {_uri(10107)}


def test_retest_bounds_are_strict_and_cannot_expand_other_formats(tmp_path):
    repo = StateRepo(open_db(tmp_path / "state.db"))
    with pytest.raises(ValueError, match="limit"):
        repo.schedule_historical_retests(
            ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=0,
        )
    with pytest.raises(ValueError, match="limit"):
        repo.schedule_historical_retests(
            ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=1000,
        )
    with pytest.raises(ValueError, match="proxy"):
        repo.schedule_historical_retests(
            ["ovpn"], ["approved"], min_ingested_at=CUTOFF, limit=1,
        )


def test_build_retests_expired_history_only_through_new_https_gate(
    tmp_path, monkeypatch
):
    repo = StateRepo(open_db(tmp_path / "build.db"))
    due = _seed(repo, 10300)
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setenv("HUNTX_HISTORICAL_RETEST_PER_FORMAT", "1")

    registry = Mock()
    registry.get.return_value = NpvtHandler()
    artifacts = Mock()
    artifacts.save_artifact.return_value = "f" * 64
    build = BuildPipeline(repo, artifacts, registry)
    route = {
        "name": "all_sources", "from_sources": ["approved"],
        "formats": ["npvt"], "min_ingested_at": CUTOFF,
    }
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "0")
    assert build.run(route) == []  # old authentication cannot bypass HTTPS
    assert artifacts.save_artifact.call_count == 0

    checked = []

    def new_https_gate(rows):
        checked.extend(x["data"]["line"] for x in rows)
        now = time.time()
        digest = _digest(due)
        accepted = [{
            "data": {
                "line": due,
                "probe_kind": "protocol_authenticated",
                "probe_authenticated": True,
                "probe_checked_at": now,
                "probe_expires_at": now + 300,
                "latency_ms": 18000,
            }
        }]
        ledger = {
            "schema_version": 1,
            "scope": "single_authenticated_https_sweep",
            "candidates": 1,
            "admitted": 1,
            "rejected": 0,
            "identities": {digest: "admitted"},
            "reasons": {"admitted": 1},
            "historical_authenticated_successes": {},
        }
        return CheckedRecords(accepted, ledger)

    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setattr("huntx.core.proxy_health.verified_records", new_https_gate)
    assert build.run(route)
    assert checked == [due]
    assert "history-secret@" in artifacts.save_artifact.call_args_list[0].args[2].decode()
    gate = next(
        payload for c in artifacts.save_output.call_args_list
        if c.args[1] == "npvt.gate.json" for payload in [json.loads(c.args[2])]
    )
    assert gate["historical_retests"]["scheduled"] == 1
    assert gate["historical_retests"]["authenticated_admitted"] == 1
    assert gate["historical_retests"]["identity_digests"] == [_digest(due)]
    assert "history-secret" not in json.dumps(gate)


def test_deferred_historical_retests_never_enter_current_working_feed(
    tmp_path, monkeypatch
):
    repo = StateRepo(open_db(tmp_path / "deferred.db"))
    old = _seed(repo, 10401)
    fresh = _seed(repo, 10402, old=False, authenticated=False)
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_HISTORICAL_RETEST_PER_FORMAT", "1")

    observed = []

    def verify(rows):
        observed.extend(x["data"]["line"] for x in rows)
        now = time.time()
        accepted = [{
            "data": {
                "line": fresh,
                "probe_kind": "protocol_authenticated",
                "probe_authenticated": True,
                "probe_checked_at": now,
                "probe_expires_at": now + 300,
                "latency_ms": 18500,
            }
        }]
        return CheckedRecords(accepted, {
            "schema_version": 1,
            "scope": "single_authenticated_https_sweep",
            "candidates": 2,
            "admitted": 1,
            "rejected": 1,
            "identities": {_digest(old): "not_completed", _digest(fresh): "admitted"},
            "reasons": {"not_completed": 1, "admitted": 1},
            "historical_authenticated_successes": {},
        })

    monkeypatch.setattr("huntx.core.proxy_health.verified_records", verify)
    registry = Mock()
    registry.get.return_value = NpvtHandler()
    artifacts = Mock()
    artifacts.save_artifact.return_value = "f" * 64
    build = BuildPipeline(repo, artifacts, registry)
    assert build.run({
        "name": "all_sources", "from_sources": ["approved"],
        "formats": ["npvt"], "min_ingested_at": CUTOFF,
    })
    assert observed == [old, fresh]
    canonical = artifacts.save_artifact.call_args_list[0].args[2].decode()
    assert "10402" in canonical
    assert "10401" not in canonical
    ledger = next(
        json.loads(c.args[2]) for c in artifacts.save_output.call_args_list
        if c.args[1] == "npvt.gate.json"
    )
    assert ledger["historical_retests"]["scheduled"] == 1
    assert ledger["historical_retests"]["attempted"] == 0
    assert ledger["historical_retests"]["deferred"] == 1
    assert ledger["historical_retests"]["authenticated_admitted"] == 0
    assert ledger["historical_retests"]["dispositions"] == {
        _digest(old): "not_completed",
    }
    with repo.db.connect() as conn:
        historical = conn.execute(
            "SELECT authenticated_successes, last_probe_at FROM proxy_lifecycle "
            "WHERE record_type = 'npvt' AND unique_hash = ?", (_digest(old),)
        ).fetchone()
        assert historical["authenticated_successes"] == 1
        assert historical["last_probe_at"] < int(time.time()) - 300


def test_thousands_of_distinct_old_successes_are_bounded_not_discarded(tmp_path):
    repo = StateRepo(open_db(tmp_path / "thousands.db"))
    observation = repo.record_file(
        "approved", "big-sub", "a" * 64, 100, "large.txt", status="processed",
    )
    uris = [_uri(port) for port in range(21000, 22024)]
    now = int(time.time())
    with repo.db.connect() as conn:
        conn.executemany(
            "INSERT INTO records(source_file_hash, source_observation_id, "
            "record_type, unique_hash, data_json, created_at) "
            "VALUES (?, ?, 'npvt', ?, ?, '2000-01-01 00:00:00')",
            [
                ("a" * 64, observation, _digest(uri), json.dumps({"line": uri}))
                for uri in uris
            ],
        )
        conn.executemany(
            "INSERT INTO proxy_lifecycle("
            "unique_hash, record_type, first_seen_at, last_seen_at, "
            "last_success_at, authenticated_successes, last_probe_at"
            ") VALUES (?, 'npvt', ?, ?, ?, 1, ?)",
            [(_digest(uri), now - 900, now - 900, now - 900, now - 900)
             for uri in uris],
        )
        conn.execute(
            "UPDATE seen_files SET ingested_at = '2000-01-01 00:00:00' "
            "WHERE id = ?", (observation,),
        )

    repo.prune_old_data(1)
    with repo.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1024
    first = repo.schedule_historical_retests(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=64
    )
    second = repo.schedule_historical_retests(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=64
    )
    first_ids = {_digest(x["data"]["line"]) for x in first}
    second_ids = {_digest(x["data"]["line"]) for x in second}
    assert len(first_ids) == len(second_ids) == 64
    assert first_ids.isdisjoint(second_ids)
    with repo.db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM proxy_retest_schedule"
        ).fetchone()[0] == 128
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1024


def test_actual_source_refresh_does_not_destroy_authenticated_retest_history(
    tmp_path
):
    repo = StateRepo(open_db(tmp_path / "refresh.db"))
    uri = _seed(repo, 10250)
    # A refresh of the very same source observation deactivates the old row
    # and replaces the seen_files timestamp; neither is a proxy revocation.
    repo.record_file(
        "approved", "message-10250", "f" * 64, 55, "new-feed.txt",
        status="processed",
    )
    with repo.db.connect() as conn:
        row = conn.execute(
            "SELECT r.is_active, s.ingested_at FROM records r "
            "JOIN seen_files s ON s.id = r.source_observation_id "
            "WHERE r.unique_hash = ?", (_digest(uri),)
        ).fetchone()
        assert row["is_active"] == 0
        assert row["ingested_at"] >= CUTOFF
    assert {r["data"]["line"] for r in repo.schedule_historical_retests(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=4,
    )} == {uri}
    # The normal fresh build remains unchanged: no stale working claim.
    assert repo.get_records_for_build(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF,
    ) == []


def test_fresh_only_release_explicitly_proves_zero_historical_candidates(
    tmp_path, monkeypatch
):
    repo = StateRepo(open_db(tmp_path / "fresh-only.db"))
    fresh = _seed(repo, 10501, old=False, authenticated=True)
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_HISTORICAL_RETEST_PER_FORMAT", "64")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")

    def current_https(rows):
        assert [item["data"]["line"] for item in rows] == [fresh]
        now = time.time()
        accepted = [{
            "data": {
                "line": fresh,
                "probe_kind": "protocol_authenticated",
                "probe_authenticated": True,
                "probe_checked_at": now,
                "probe_expires_at": now + 300,
                "latency_ms": 19000,
            }
        }]
        return CheckedRecords(accepted, {
            "schema_version": 1,
            "scope": "single_authenticated_https_sweep",
            "candidates": 1,
            "admitted": 1,
            "rejected": 0,
            "identities": {_digest(fresh): "admitted"},
            "reasons": {"admitted": 1},
            "historical_authenticated_successes": {},
        })

    monkeypatch.setattr("huntx.core.proxy_health.verified_records", current_https)
    registry = Mock()
    registry.get.return_value = NpvtHandler()
    artifacts = Mock()
    artifacts.save_artifact.return_value = "f" * 64
    route = {
        "name": "all_sources", "from_sources": ["approved"],
        "formats": ["npvt"], "min_ingested_at": CUTOFF,
    }
    assert BuildPipeline(repo, artifacts, registry).run(route)
    gate = next(
        json.loads(call.args[2]) for call in artifacts.save_output.call_args_list
        if call.args[1] == "npvt.gate.json"
    )
    retest = gate["historical_retests"]
    assert retest["selection_status"] == "performed"
    assert retest["scheduled"] == 0
    assert retest["attempted"] == 0
    assert retest["deferred"] == 0
    assert retest["authenticated_admitted"] == 0
    assert retest["identity_digests"] == []
    assert retest["dispositions"] == {}
    with repo.db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM proxy_retest_schedule"
        ).fetchone()[0] == 0


def test_explicit_zero_retest_budget_is_distinct_from_empty_candidate_pool(
    tmp_path, monkeypatch
):
    repo = StateRepo(open_db(tmp_path / "disabled-retest.db"))
    fresh = _seed(repo, 10502, old=False, authenticated=True)
    old = _seed(repo, 10503)
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_HISTORICAL_RETEST_PER_FORMAT", "0")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")

    def current_https(rows):
        assert [item["data"]["line"] for item in rows] == [fresh]
        now = time.time()
        return CheckedRecords([{
            "data": {
                "line": fresh, "probe_kind": "protocol_authenticated",
                "probe_authenticated": True, "probe_checked_at": now,
                "probe_expires_at": now + 300, "latency_ms": 19000,
            }
        }], {
            "schema_version": 1, "scope": "single_authenticated_https_sweep",
            "candidates": 1, "admitted": 1, "rejected": 0,
            "identities": {_digest(fresh): "admitted"},
            "reasons": {"admitted": 1},
            "historical_authenticated_successes": {},
        })
    monkeypatch.setattr("huntx.core.proxy_health.verified_records", current_https)
    registry = Mock()
    registry.get.return_value = NpvtHandler()
    artifacts = Mock()
    artifacts.save_artifact.return_value = "f" * 64
    assert BuildPipeline(repo, artifacts, registry).run({
        "name": "all_sources", "from_sources": ["approved"],
        "formats": ["npvt"], "min_ingested_at": CUTOFF,
    })
    gate = next(
        json.loads(call.args[2]) for call in artifacts.save_output.call_args_list
        if call.args[1] == "npvt.gate.json"
    )
    assert gate["historical_retests"]["selection_status"] == "disabled_by_config"
    assert gate["historical_retests"]["scheduled"] == 0
    assert gate["historical_retests"]["identity_digests"] == []
    assert old.encode("utf-8") not in artifacts.save_artifact.call_args_list[0].args[2]
    with repo.db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM proxy_retest_schedule"
        ).fetchone()[0] == 0
