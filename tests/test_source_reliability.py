"""Historical HTTP source-retrieval diagnostics (not proxy connectivity)."""
from huntx.core.orchestrator import Orchestrator
from huntx.core.source_reliability import summarize_source_reliability


def test_unobserved_source_never_receives_optimistic_reliability():
    summary = summarize_source_reliability({}, now=1_800_000_000)
    assert summary["kind"] == "source_http_availability_only"
    assert summary["wilson_lower_bound"] == 0
    assert summary["freshness"] == "unobserved"


def test_one_success_is_not_misrepresented_as_proven_reliable():
    summary = summarize_source_reliability(
        {"previous_successes": 1, "last_success_at": 1_800_000_000},
        now=1_800_000_000,
    )
    assert 0 < summary["wilson_lower_bound"] < 0.3
    assert summary["freshness"] == "recent"
    assert summary["success_age_seconds"] == 0


def test_history_distinguishes_staleness_from_recent_source_failure():
    old = summarize_source_reliability(
        {"previous_successes": 120, "last_success_at": 1_790_000_000},
        now=1_800_000_000,
    )
    assert old["freshness"] == "stale"
    degraded = summarize_source_reliability(
        {"previous_successes": 5, "total_failures": 2,
         "consecutive_failures": 2, "last_success_at": 1_799_999_900},
        now=1_800_000_000,
    )
    assert degraded["freshness"] == "degraded"
    assert degraded["last_success_at"] == 1_799_999_900


def test_malformed_state_never_creates_fake_freshness():
    values = {
        "previous_successes": float("inf"), "total_failures": True,
        "consecutive_failures": -100, "last_success_at": float("nan"),
        "last_failed_at": 9_999_999_999,
    }
    summary = summarize_source_reliability(values, now=1_800_000_000)
    assert summary["wilson_lower_bound"] == 0
    assert summary["last_success_at"] is None
    assert summary["last_failed_at"] is None


def test_timeout_history_preserves_last_successful_feed_state():
    class Repo:
        def __init__(self):
            self.state = {
                "feed_sha256": "a" * 64, "normalized_sha256": "b" * 64,
                "previous_successes": 3, "total_failures": 0,
            }

        def get_source_state(self, source_id):
            return dict(self.state)

        def update_source_state(self, source_id, state, source_type="telegram"):
            assert source_type == "http_subscription"
            self.state = dict(state)

    app = Orchestrator.__new__(Orchestrator)
    app.repo = Repo()
    app._http_source_reports = {}
    app._record_http_source_failure("src_http_test", "TimeoutError")
    assert app.repo.state["feed_sha256"] == "a" * 64
    assert app.repo.state["normalized_sha256"] == "b" * 64
    assert app.repo.state["previous_successes"] == 3
    assert app.repo.state["total_failures"] == 1
    assert app.repo.state["consecutive_failures"] == 1
    assert app._http_source_reports["src_http_test"]["error_type"] == "TimeoutError"
    assert app._http_source_reports["src_http_test"]["availability"]["failures"] == 1


def test_recent_source_history_prevents_lifetime_success_from_masking_recent_failure():
    from huntx.core.source_reliability import append_retrieval_observation

    now = 1_800_000_000
    state = {"previous_successes": 900, "total_failures": 2, "last_success_at": now}
    for _ in range(6):
        state["retrieval_history"] = append_retrieval_observation(
            state, success=False, now=now
        )
    result = summarize_source_reliability(state, now=now)
    assert result["wilson_lower_bound"] > 0.9
    assert result["rolling_samples"] == 6
    assert result["rolling_successes"] == 0
    assert result["rolling_wilson_lower_bound"] == 0
    assert result["ranking_score"] == 0
    assert result["evidence"] == "feed_retrieval_not_authenticated_proxy"


def test_recent_source_events_are_bounded_and_cache_hits_do_not_invent_success():
    from huntx.core.source_reliability import append_retrieval_observation

    now = 1_800_000_000
    state = {"last_success_at": now}
    for number in range(200):
        state["retrieval_history"] = append_retrieval_observation(
            state, success=(number % 2 == 0), now=now,
            nodes=10, cache_revalidated=True,
        )
    assert len(state["retrieval_history"]) == 64
    report = summarize_source_reliability(state, now=now)
    assert report["rolling_samples"] == 64
    assert report["rolling_successes"] == 32
    assert report["cache_revalidations"] == 32
    assert 0 < report["rolling_wilson_lower_bound"] < 0.5
    assert len(str(state["retrieval_history"])) < 5000


def test_corrupt_and_expired_history_does_not_fake_recent_reliability():
    from huntx.core.source_reliability import append_retrieval_observation

    now = 1_800_000_000
    state = {
        "retrieval_history": [
            {"at": now - 31 * 86400, "ok": True, "nodes": 1},
            {"at": now + 1000, "ok": True},
            {"at": now, "ok": "true"},
            None,
            {"at": now, "ok": False, "nodes": 999},
        ],
    }
    summary = summarize_source_reliability(state, now=now)
    assert summary["rolling_samples"] == 1
    assert summary["rolling_successes"] == 0
    events = append_retrieval_observation(state, success=True, now=now, nodes=2)
    assert len(events) == 2
    assert events[-1]["nodes"] == 2


def test_http_priority_preserves_telegram_order_and_explores_oldest_source():
    from types import SimpleNamespace
    from huntx.core.source_reliability import prioritize_http_sources

    now = 1_800_000_000
    sources = [
        SimpleNamespace(id="tg_a", type="telegram_user"),
        SimpleNamespace(id="http_new", type="http_subscription"),
        SimpleNamespace(id="http_old", type="http_subscription"),
        SimpleNamespace(id="tg_b", type="telegram_user"),
        SimpleNamespace(id="http_good", type="http_subscription"),
    ]
    states = {
        "http_old": {
            "checked_at": now - 9000, "previous_successes": 10,
            "last_success_at": now - 9000,
        },
        "http_good": {
            "checked_at": now - 200, "previous_successes": 100,
            "last_success_at": now - 200, "retrieval_history": [
                {"at": now - i, "ok": True} for i in range(20)
            ],
        },
    }
    ordered = prioritize_http_sources(sources, states, now=now)
    assert ordered[0].id == "tg_a" and ordered[3].id == "tg_b"
    assert ordered[1].id == "http_new"  # Never observed, priority exploration.
    assert ordered[2].id == "http_good"
    assert ordered[4].id == "http_old"
    assert {source.id for source in ordered} == {source.id for source in sources}
