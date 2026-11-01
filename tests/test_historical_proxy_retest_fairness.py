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
    _seed(repo, 10105, inactive=True)
    _seed(repo, 10106, old=False)
    _seed(repo, 10107, kind="npvtsub")

    rows = repo.schedule_historical_retests(
        ["npvt"], ["approved"], min_ingested_at=CUTOFF, limit=32,
    )
    assert {r["data"]["line"] for r in rows} == {due}
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
