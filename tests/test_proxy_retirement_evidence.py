"""Only repeated independent authenticated failures may temporarily suppress feeds.

Permanent retirement requires an explicit verified policy decision, never
transient TCP failure, DNS timeout, old snapshots or another source's opinion.
"""
import json
import time

from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.proxy_lifecycle import (
    record_authenticated_probe, terminalize_proxy, describe_proxy,
)
from huntx.state.verdict_store import get_records_for_governed_build, upsert_record_verdict
from huntx.state.proxy_retirement import get_retirement_audit


DIGEST = "a" * 64


def setup_proxy(tmp_path):
    db = open_db(tmp_path / "records.db")
    repo = StateRepo(db)
    raw = "b" * 64
    seen = repo.record_file("trusted", "observ-1", raw, 50, "nodes.txt")
    repo.add_records_batch([(raw, seen, "npvt", DIGEST, json.dumps({
        "line": "vless://user@vpn.example.com:443"
    }))])
    upsert_record_verdict(
        db, unique_hash=DIGEST, record_type="npvt",
        syntax_status="pass", parser_version="v1",
        probe_status="unknown", policy_status="pass",
        policy_version="v1", policy_tier="secure",
    )
    return db, repo


def build_both(db, repo):
    compatible = repo.get_records_for_build(["npvt"], ["trusted"])
    secure = get_records_for_governed_build(
        db, ["npvt"], ["trusted"], publication_tier="secure"
    )
    return len(compatible), len(secure)


def record_failures(db, *, distinct=True, spread=True, count=6, first=None):
    now = int(time.time())
    start = first if first is not None else now - (5 * 86400 if spread else 100)
    for index in range(count):
        record_authenticated_probe(
            db, unique_hash=DIGEST, record_type="npvt",
            probe_id=f"failure-{index}", success=False,
            vantage_id=("east" if index % 2 else "west") if distinct else "east",
            checked_at=start + index * (86400 if spread else 2),
        )


def test_three_repeated_failures_are_not_enough_for_auto_suppression(tmp_path):
    db, repo = setup_proxy(tmp_path)
    record_failures(db, count=3)
    assert build_both(db, repo) == (1, 1)
    assert describe_proxy(db, unique_hash=DIGEST, record_type="npvt")["lifecycle_status"] == "suspect"


def test_six_independent_failures_over_days_temporarily_suppress_both_feeds(tmp_path):
    db, repo = setup_proxy(tmp_path)
    record_failures(db)
    assert build_both(db, repo) == (0, 0)
    audit = get_retirement_audit(db)
    assert audit["suppressed_candidates"] == 1
    assert audit["permanent_exclusions"] == 0
    assert audit["insufficient_evidence"] == 0


def test_single_vantage_or_single_hour_cannot_suppress(tmp_path):
    for distinct, spread in ((False, True), (True, False)):
        db, repo = setup_proxy(tmp_path / f"{distinct}-{spread}")
        record_failures(db, distinct=distinct, spread=spread)
        assert build_both(db, repo) == (1, 1)
        assert get_retirement_audit(db)["insufficient_evidence"] == 1


def test_authenticated_recovery_reenables_transiently_suppressed_proxy(tmp_path):
    db, repo = setup_proxy(tmp_path)
    record_failures(db)
    assert build_both(db, repo) == (0, 0)
    record_authenticated_probe(
        db, unique_hash=DIGEST, record_type="npvt",
        probe_id="verified-recovery", vantage_id="west",
        success=True, checked_at=int(time.time()),
    )
    assert build_both(db, repo) == (1, 1)
    assert get_retirement_audit(db)["suppressed_candidates"] == 0


def test_stale_failures_do_not_prove_permanent_death(tmp_path):
    db, repo = setup_proxy(tmp_path)
    record_failures(db, first=int(time.time()) - 16 * 86400)
    assert build_both(db, repo) == (1, 1)


def test_permanent_retirement_requires_explicit_policy_and_is_never_revived(tmp_path):
    db, repo = setup_proxy(tmp_path)
    terminalize_proxy(
        db, unique_hash=DIGEST, record_type="npvt",
        reason_code="verified_revocation", status="revoked",
    )
    assert build_both(db, repo) == (0, 0)
    audit = get_retirement_audit(db)
    assert audit["permanent_exclusions"] == 1
    assert audit["suppressed_candidates"] == 0


def test_tcp_only_evidence_cannot_count_towards_quarantine(tmp_path):
    db, repo = setup_proxy(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="authenticated"):
        record_authenticated_probe(
            db, unique_hash=DIGEST, record_type="npvt",
            probe_id="tcp-attempt", vantage_id="west",
            success=False, evidence_kind="tcp_connect",
        )
    assert build_both(db, repo) == (1, 1)
