from huntx.core.self_healing import SelfHealingDaemon


def test_self_healing_backoff_and_retest():
    daemon = SelfHealingDaemon(db_path=":memory:", backoff_schedule=[10, 30, 60])
    now = 1000.0

    fail_count, next_check = daemon.record_failure("h1", "vless://u@h1:443", current_time=now)
    assert fail_count == 1
    assert next_check == 1010.0

    # Check due for retest before 1010.0
    due = daemon.get_due_for_retest(current_time=1005.0)
    assert len(due) == 0

    # Check due for retest at 1010.0
    due = daemon.get_due_for_retest(current_time=1010.0)
    assert len(due) == 1
    assert due[0]["unique_hash"] == "h1"

    # Second failure escalates backoff to +30s
    fail_count, next_check = daemon.record_failure("h1", "vless://u@h1:443", current_time=1010.0)
    assert fail_count == 2
    assert next_check == 1040.0


def test_self_healing_reinstate_and_purge():
    daemon = SelfHealingDaemon(db_path=":memory:")
    now = 100000.0

    daemon.record_failure("h1", "vless://u@h1:443", current_time=now)
    daemon.record_failure("h2", "vmess://u@h2:443", current_time=now - (49 * 3600))  # 49h ago

    # Purge stale >48h
    purged_count = daemon.purge_stale_proxies(max_age_hours=48, current_time=now)
    assert purged_count == 1

    # Reinstate recovered node h1
    reinstated = daemon.reinstate_proxy("h1")
    assert reinstated is True
    assert daemon.reinstate_proxy("h1") is False


def test_run_poller_cycle_returns_stats_dict():
    """
    Plan contract: run_poller_cycle() -> Dict[str, int] with keys
    retested, reinstated, purged.
    A proxy past its next_check_at should appear in retested count.
    A proxy older than 48h should appear in purged count.
    """
    daemon = SelfHealingDaemon(db_path=":memory:", backoff_schedule=[10, 30, 60])
    now = 100000.0

    # Record a failure that is already due for retest (next_check_at = now+10, test at now+20)
    daemon.record_failure("due_proxy", "vless://u@due:443", current_time=now)
    # Record a stale proxy that has been failing for 49 hours
    daemon.record_failure("stale_proxy", "vmess://u@stale:443", current_time=now - (49 * 3600))

    # Run poller cycle at now+20 (due_proxy is past its 10s retry window)
    result = daemon.run_poller_cycle(current_time=now + 20)

    assert isinstance(result, dict), "run_poller_cycle must return a dict"
    assert "retested" in result
    assert "purged" in result
    assert result["retested"] >= 1, "due_proxy should have been retested"
    assert result["purged"] >= 1, "stale_proxy should have been purged"


def test_run_poller_cycle_empty_db_returns_zeros():
    """run_poller_cycle on empty DB must return zeros, not raise."""
    daemon = SelfHealingDaemon(db_path=":memory:")
    result = daemon.run_poller_cycle()
    assert result == {"retested": 0, "reinstated": 0, "purged": 0}
