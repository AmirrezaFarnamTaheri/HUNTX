"""Pruning must not discard legitimately authenticated working-proxy history.

Historic identities remain internal retest candidates. They do not become a
freshly authenticated public feed unless their HTTPS handshake is revalidated.
"""
import json
import time

from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.proxy_lifecycle import (
    record_authenticated_probe,
    terminalize_proxy,
)


def make_observation(tmp_path, unique_hash, *, record_type="npvt"):
    repo = StateRepo(open_db(tmp_path / "history.db"))
    observed = repo.record_file("approved", "old-1", "b" * 64, 90,
                                "old-proxy.txt", status="processed")
    repo.add_records_batch([("b" * 64, observed, record_type, unique_hash,
                             json.dumps({"line": "trojan://secret@5.5.5.5:443"}))])
    with repo.db.connect() as conn:
        conn.execute("UPDATE records SET created_at = '2000-01-01 00:00:00'")
        conn.execute("UPDATE seen_files SET ingested_at = '2000-01-01 00:00:00'")
    return repo, observed


def counts(repo, observed):
    with repo.db.connect() as conn:
        record_count = conn.execute(
            "SELECT COUNT(*) FROM records WHERE source_observation_id = ?",
            (observed,),
        ).fetchone()[0]
        seen_count = conn.execute(
            "SELECT COUNT(*) FROM seen_files WHERE id = ?", (observed,)
        ).fetchone()[0]
    return record_count, seen_count


def test_old_authenticated_success_keeps_observation_and_record_for_retest(tmp_path):
    digest = "a" * 64
    repo, observed = make_observation(tmp_path, digest)
    record_authenticated_probe(
        repo.db, unique_hash=digest, record_type="npvt",
        probe_id="success-1", vantage_id="verified-a",
        success=True, checked_at=int(time.time()),
    )
    repo.prune_old_data(1)
    assert counts(repo, observed) == (1, 1)
    # Preserving history is NOT permission to publish old nodes as current.
    assert repo.get_records_for_build(
        ["npvt"], ["approved"], min_ingested_at="2026-10-30 00:00:00"
    ) == []


def test_temporary_authenticated_failure_does_not_erase_previously_working_proxy(tmp_path):
    digest = "c" * 64
    repo, observed = make_observation(tmp_path, digest)
    now = int(time.time())
    record_authenticated_probe(
        repo.db, unique_hash=digest, record_type="npvt",
        probe_id="worked", vantage_id="west", success=True, checked_at=now - 2,
    )
    record_authenticated_probe(
        repo.db, unique_hash=digest, record_type="npvt",
        probe_id="temporary-failure", vantage_id="east", success=False, checked_at=now,
    )
    repo.prune_old_data(1)
    assert counts(repo, observed) == (1, 1)


def test_explicit_revocation_allows_expired_proxy_record_to_be_pruned(tmp_path):
    digest = "d" * 64
    repo, observed = make_observation(tmp_path, digest)
    record_authenticated_probe(
        repo.db, unique_hash=digest, record_type="npvt",
        probe_id="worked", vantage_id="east",
        success=True, checked_at=int(time.time()),
    )
    terminalize_proxy(
        repo.db, unique_hash=digest, record_type="npvt",
        reason_code="verified_revocation", status="revoked",
    )
    repo.prune_old_data(1)
    assert counts(repo, observed) == (0, 0)


def test_unverified_expired_record_still_prunes_normally(tmp_path):
    repo, observed = make_observation(tmp_path, "e" * 64)
    repo.prune_old_data(1)
    assert counts(repo, observed) == (0, 0)


def test_actual_production_build_persists_authenticated_success_for_future_retests(
    tmp_path, monkeypatch
):
    """Do not rely on a lifecycle row that the real producer never updates."""
    import hashlib
    from unittest.mock import Mock

    from huntx.core.proxy_health import CheckedRecords
    from huntx.formats.npvt import NpvtHandler, canonical_proxy_identity
    from huntx.pipeline.build import BuildPipeline

    uri = "trojan://secret@5.5.5.5:443?security=tls#Eligible"
    digest = hashlib.sha256(canonical_proxy_identity(uri).encode("utf-8")).hexdigest()
    repo = StateRepo(open_db(tmp_path / "working.db"))
    observation = repo.record_file("approved", "message-1", "c" * 64, 90,
                                   "nodes.txt", status="processed")
    repo.add_record("c" * 64, "npvt", digest, {"line": uri},
                    source_observation_id=observation)
    with repo.db.connect() as conn:
        conn.execute("UPDATE records SET created_at = '2000-01-01 00:00:00'")
        conn.execute("UPDATE seen_files SET ingested_at = '2000-01-01 00:00:00'")
    now = time.time()
    admitted = [{
        "data": {"line": uri, "probe_kind": "protocol_authenticated",
                 "probe_authenticated": True, "probe_checked_at": now,
                 "probe_expires_at": now + 300, "latency_ms": 17}
    }]
    ledger = {
        "schema_version": 1, "scope": "single_authenticated_https_sweep",
        "candidates": 1, "admitted": 1, "rejected": 0,
        "identities": {digest: "admitted"}, "reasons": {"admitted": 1},
    }
    monkeypatch.setenv("HUNTX_REQUIRE_PROXY_HEALTH", "1")
    monkeypatch.setenv("HUNTX_REMARK_STYLE", "legacy")
    monkeypatch.setattr(
        "huntx.core.proxy_health.verified_records",
        lambda records: CheckedRecords(admitted, ledger),
    )
    registry = Mock()
    registry.get.return_value = NpvtHandler()
    artifacts = Mock()
    artifacts.save_artifact.return_value = "f" * 64
    pipeline = BuildPipeline(repo, artifacts, registry)
    results = pipeline.run({
        "name": "all_sources", "from_sources": ["approved"], "formats": ["npvt"],
    })
    assert results
    with repo.db.connect() as conn:
        lifecycle = conn.execute(
            "SELECT authenticated_successes FROM proxy_lifecycle "
            "WHERE unique_hash = ? AND record_type = 'npvt'", (digest,)
        ).fetchone()
        persisted = conn.execute(
            "SELECT probe_id, unique_hash FROM proxy_probe_history "
            "WHERE unique_hash = ?", (digest,)
        ).fetchall()
    assert lifecycle is not None and lifecycle["authenticated_successes"] == 1
    assert len(persisted) == 1
    assert "secret@" not in str([dict(item) for item in persisted])
    repo.prune_old_data(1)
    assert counts(repo, observation) == (1, 1)


def test_unmatched_sidecar_identity_cannot_forge_durable_authentication(tmp_path):
    import hashlib

    from huntx.formats.npvt import canonical_proxy_identity

    repo = StateRepo(open_db(tmp_path / "forge.db"))
    uri = "trojan://secret@5.5.5.5:443?security=tls"
    digest = hashlib.sha256(canonical_proxy_identity(uri).encode()).hexdigest()
    evidence = json.dumps({
        "schema_version": 1, "evidence": "publisher_authenticated_https",
        "admitted_count": 1,
        "records": {"a" * 64: {
            "checked_at": time.time(), "expires_at": time.time() + 300,
            "duration_ms": 50,
        }},
    }).encode()
    import pytest
    with pytest.raises(ValueError, match="(sidecar|identity|mismatch|digest)"):
        repo.persist_authenticated_build_evidence("npvt", (uri + "\n").encode(), evidence)
    with repo.db.connect() as conn:
        recorded = conn.execute(
            "SELECT COUNT(*) FROM proxy_probe_history WHERE unique_hash = ?",
            (digest,),
        ).fetchone()[0]
    assert recorded == 0
