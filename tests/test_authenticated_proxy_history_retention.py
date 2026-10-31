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
