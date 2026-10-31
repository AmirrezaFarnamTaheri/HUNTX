"""Regression matrix for nonblocking Telegram source availability."""
import pytest
from scripts.verify_telegram_activity import EvidenceContractError, evaluate


def summary(**changes):
    data = {"sources_checked": 32, "messages_scanned": 0, "lifo_windows_completed": 0,
            "lifo_residue": {"remaining": 1478}}
    data.update(changes)
    return {"schema_version": 1, "summary": data}


def health(count=81):
    return {"schema_version": 1, "sources": [
        {"id": f"tg-{i}", "type": "telegram_user", "enabled": True, "status": "retrying"}
        for i in range(count)
    ]}


def test_real_production_floodwait_nonfatal():
    log = ("[MTProto] Connected.\n[MTProto] Resolved peer -100123 -> channel_id=123\n"
           "[LIFO] MTProto canonical preflight rate-limited for 505s; "
           "postponed 992 already queued window(s)\n")
    verdict = evaluate(log, summary(), source_run_id=41173605265, source_health=health())
    assert verdict["status"] == "rate_limited"
    assert verdict["retry_delay_seconds"] == 505
    assert verdict["run_summary_windows_pending"] == 1478
    assert verdict["verified_telegram_ingestion"] is False


def test_unavailable_is_not_fatal():
    result = evaluate("Telegram unavailable", summary(), source_run_id=1, source_health=health())
    assert result["status"] == "unavailable"
    assert result["availability_nonblocking"] is True


def test_completed_window_actually_verified():
    log = ("[MTProto] Connected.\n[MTProto] Resolved peer -100123 -> channel_id=123\n"
           "[LIFO] source=tg-0 scanned=3 ingested=2 completed=True\n")
    result = evaluate(log, summary(sources_checked=1, messages_scanned=3, lifo_windows_completed=1),
                      source_run_id=1, source_health=health(1))
    assert result["verified_telegram_ingestion"] is True
    assert result["completed_window_messages_ingested"] == 2


def test_empty_completed_window_is_neutral():
    log = ("[MTProto] Connected.\n[MTProto] Resolved peer -100123 -> channel_id=123\n"
           "[LIFO] source=tg-0 scanned=0 ingested=0 completed=True\n")
    result = evaluate(log, summary(sources_checked=1, lifo_windows_completed=1),
                      source_run_id=1, source_health=health(1))
    assert result["status"] == "completed_empty"
    assert not result["verified_telegram_ingestion"]


@pytest.mark.parametrize("changes", [
    {"messages_scanned": True}, {"sources_checked": -1},
    {"lifo_windows_completed": "1"}])
def test_invalid_metrics_are_errors(changes):
    with pytest.raises(EvidenceContractError):
        evaluate("Telegram unavailable", summary(**changes), source_run_id=1, source_health=health())


def test_counter_contradiction_is_error():
    with pytest.raises(EvidenceContractError, match="exceeds"):
        evaluate("[LIFO] source=tg-0 scanned=5 ingested=3 completed=True",
                 summary(messages_scanned=0, lifo_windows_completed=0),
                 source_run_id=1, source_health=health())


def test_http_checked_counter_cannot_verify_telegram():
    result = evaluate("[MTProto] Connected.", summary(sources_checked=32, messages_scanned=12,
                      lifo_windows_completed=2), source_run_id=1, source_health=health())
    assert result["status"] == "inconclusive"
    assert result["verified_telegram_ingestion"] is False


def test_zero_configured_sources():
    assert evaluate("No Telegram", summary(), source_run_id=1,
                    source_health=health(0))["status"] == "not_configured"


def test_real_artifact_shape_exposes_nested_residue():
    result = evaluate("[LIFO] MTProto canonical preflight rate-limited for 505s",
                      summary(), source_run_id=1, source_health=health())
    assert result["run_summary_windows_pending"] == 1478


def test_telegram_source_counts_are_not_bounded_by_http_source_counts():
    log = "[MTProto] Connected.\n[MTProto] Resolved peer peer -> channel_id=1\n"
    log += "".join(f"[LIFO] source=tg-{i} scanned=1 ingested=1 completed=True\n" for i in range(40))
    result = evaluate(log, summary(sources_checked=32, messages_scanned=40, lifo_windows_completed=40),
                      source_run_id=1, source_health=health(81))
    assert result["status"] == "verified_activity"
    assert result["telegram_sources_observed"] == 40


def test_unknown_source_with_completed_window_is_contradictory_evidence():
    log = "[MTProto] Connected.\n[MTProto] Resolved peer peer -> channel_id=1\n"
    log += "[LIFO] source=rogue scanned=1 ingested=1 completed=True\n"
    with pytest.raises(EvidenceContractError, match="not an enabled Telegram source"):
        evaluate(log, summary(messages_scanned=1, lifo_windows_completed=1),
                 source_run_id=1, source_health=health(1))
