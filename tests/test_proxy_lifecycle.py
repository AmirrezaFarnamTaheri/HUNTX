"""Non-revivable historical proxy decisions across source changes and restarts."""
import json

import pytest

from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.state.proxy_lifecycle import (
    describe_proxy, record_authenticated_probe, terminalize_proxy,
)


def _seed(db, *, external_id: str = "old", source: str = "source_a"):
    repo = StateRepo(db)
    digest = "a" * 64
    raw = "f" * 64
    observation = repo.record_file(source, external_id, raw, 80, "feed.txt")
    repo.add_records_batch([
        (raw, observation, "npvt", digest, json.dumps({"line": "placeholder"}))
    ])
    return repo, digest


def test_passive_redetection_from_another_feed_cannot_resurrect_terminal_hash(tmp_path):
    db = open_db(tmp_path / "state.db")
    repo, digest = _seed(db)
    assert len(repo.get_records_for_build(["npvt"], ["source_a"])) == 1
    terminalize_proxy(db, unique_hash=digest, record_type="npvt", reason_code="revoked_operator")
    assert repo.get_records_for_build(["npvt"], ["source_a"]) == []
    _seed(db, external_id="new", source="source_b")
    assert repo.get_records_for_build(["npvt"], ["source_a", "source_b"]) == []
    assert describe_proxy(db, unique_hash=digest, record_type="npvt")["lifecycle_status"] == "dead"
    with pytest.raises(ValueError, match="terminal"):
        record_authenticated_probe(
            db, unique_hash=digest, record_type="npvt",
            probe_id="probe_1", vantage_id="eu", success=True,
        )
    # New process, same persistent DB: terminal policy is not lost.
    again = open_db(tmp_path / "state.db")
    assert StateRepo(again).get_records_for_build(["npvt"], ["source_b"]) == []


def test_protocol_evidence_is_idempotent_and_tcp_does_not_authorize_probes(tmp_path):
    db = open_db(tmp_path / "state.db")
    _, digest = _seed(db)
    with pytest.raises(ValueError, match="authenticated"):
        record_authenticated_probe(
            db, unique_hash=digest, record_type="npvt",
            probe_id="tcp_only", vantage_id="eu", success=True,
            evidence_kind="tcp_connect",
        )
    assert record_authenticated_probe(
        db, unique_hash=digest, record_type="npvt",
        probe_id="protocol_1", vantage_id="eu", success=True, latency_ms=25,
    )
    assert not record_authenticated_probe(
        db, unique_hash=digest, record_type="npvt",
        probe_id="protocol_1", vantage_id="eu", success=True, latency_ms=25,
    )
    row = describe_proxy(db, unique_hash=digest, record_type="npvt")
    assert row["lifecycle_status"] == "active"
    assert row["authenticated_successes"] == 1


def test_failure_streak_degrades_and_recovers_only_with_new_authenticated_probe(tmp_path):
    db = open_db(tmp_path / "state.db")
    _, digest = _seed(db)
    for i in range(3):
        record_authenticated_probe(
            db, unique_hash=digest, record_type="npvt",
            probe_id=f"failure_{i}", vantage_id="us", success=False,
        )
    row = describe_proxy(db, unique_hash=digest, record_type="npvt")
    assert row["lifecycle_status"] == "suspect"
    assert row["consecutive_failures"] == 3
    record_authenticated_probe(
        db, unique_hash=digest, record_type="npvt",
        probe_id="recovery", vantage_id="eu", success=True,
    )
    row = describe_proxy(db, unique_hash=digest, record_type="npvt")
    assert row["lifecycle_status"] == "active"
    assert row["consecutive_failures"] == 0
    assert row["authenticated_successes"] == 1
    assert row["authenticated_failures"] == 3


def test_schema_migration_retains_existing_state(tmp_path):
    db = open_db(tmp_path / "old.db")
    with db.connect() as c:
        c.execute("PRAGMA user_version = 11")
        c.execute(
            "INSERT INTO source_state (source_id, source_type, state_json) "
            "VALUES ('legacy', 'telegram', '{}')"
        )
    reopened = open_db(tmp_path / "old.db")
    with reopened.connect() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        count = c.execute(
            "SELECT COUNT(*) FROM source_state WHERE source_id = 'legacy'"
        ).fetchone()[0]
    assert version == 13
    assert count == 1


def test_old_delayed_success_cannot_reactivate_newer_failed_probe(tmp_path):
    import time

    db = open_db(tmp_path / "state.db")
    _, digest = _seed(db)
    now = int(time.time())
    record_authenticated_probe(
        db, unique_hash=digest, record_type="npvt",
        probe_id="new_failure", vantage_id="eu", success=False,
        checked_at=now,
    )
    with pytest.raises(ValueError, match="out-of-order"):
        record_authenticated_probe(
            db, unique_hash=digest, record_type="npvt",
            probe_id="old_success", vantage_id="eu", success=True,
            checked_at=now - 90,
        )
    result = describe_proxy(db, unique_hash=digest, record_type="npvt")
    assert result["lifecycle_status"] == "degraded"
    assert result["authenticated_successes"] == 0
    assert result["authenticated_failures"] == 1
    assert result["last_probe_result"] == "fail"
    assert not record_authenticated_probe(
        db, unique_hash=digest, record_type="npvt",
        probe_id="new_failure", vantage_id="eu", success=False,
        checked_at=now,
    )


def test_secure_governed_build_cannot_publish_revoked_identity(tmp_path):
    from huntx.state.verdict_store import (
        get_records_for_governed_build, upsert_record_verdict,
    )

    db = open_db(tmp_path / "state.db")
    _, digest = _seed(db)
    upsert_record_verdict(
        db,
        unique_hash=digest, record_type="npvt",
        syntax_status="pass", parser_version="parser-test",
        probe_status="unknown", policy_status="pass",
        policy_version="policy-test", policy_tier="secure",
    )
    arguments = dict(
        record_types=["npvt"], allowed_source_ids=["source_a"],
        publication_tier="secure", require_fresh_probe=False,
    )
    assert get_records_for_governed_build(db, **arguments)
    terminalize_proxy(
        db, unique_hash=digest, record_type="npvt",
        reason_code="revoked_credentials", status="revoked",
    )
    assert get_records_for_governed_build(db, **arguments) == []
