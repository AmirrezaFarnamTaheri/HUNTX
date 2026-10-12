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
