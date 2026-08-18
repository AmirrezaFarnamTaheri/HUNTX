"""
H-5 Source Lifecycle State-Machine Regression Suite.

Verifies that record_source_event enforces the allowed transition graph
and that illegal transitions raise ValueError without mutating state.

Transition table:
  candidate  -> candidate | approved | quarantined | retired
  approved   -> approved  | degraded | quarantined | retired
  degraded   -> degraded  | approved | quarantined | retired
  quarantined-> quarantined | candidate | retired
  retired    -> retired   (terminal)
"""
import pathlib
import tempfile
import pytest

from huntx.state.db import open_db
from huntx.state.lifecycle import record_source_event, get_source_lifecycle

T = 1_000_000.0  # arbitrary stable timestamp


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return open_db(pathlib.Path(tmp.name))


def _seed(db, source_id, trust_state, t=T):
    record_source_event(db, source_id, "test_type", trust_state, "attempt", observed_at=t)


# ---------------------------------------------------------------------------
# Valid transitions — must not raise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_state,to_state", [
    ("candidate", "candidate"),
    ("candidate", "approved"),
    ("candidate", "quarantined"),
    ("candidate", "retired"),
    ("approved", "approved"),
    ("approved", "degraded"),
    ("approved", "quarantined"),
    ("approved", "retired"),
    ("degraded", "degraded"),
    ("degraded", "approved"),
    ("degraded", "quarantined"),
    ("degraded", "retired"),
    ("quarantined", "quarantined"),
    ("quarantined", "candidate"),
    ("quarantined", "retired"),
    ("retired", "retired"),
])
def test_valid_transition_does_not_raise(from_state, to_state):
    """H-5: Legal state transitions must not raise."""
    db = _make_db()
    _seed(db, "s1", from_state, t=T)
    # Should succeed
    record_source_event(db, "s1", "test_type", to_state, "attempt", observed_at=T + 1)
    lc = get_source_lifecycle(db, "s1")
    assert lc["trust_state"] == to_state


# ---------------------------------------------------------------------------
# Illegal transitions — must raise ValueError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_state,to_state", [
    ("approved",    "candidate"),   # cannot go back to candidate
    ("degraded",    "candidate"),   # cannot go back to candidate
    ("retired",     "candidate"),   # retired is terminal
    ("retired",     "approved"),
    ("retired",     "degraded"),
    ("retired",     "quarantined"),
    ("quarantined", "approved"),    # must re-enter via candidate
    ("quarantined", "degraded"),
])
def test_illegal_transition_raises_value_error(from_state, to_state):
    """H-5: Illegal state transitions must raise ValueError."""
    db = _make_db()
    _seed(db, "s2", from_state, t=T)
    with pytest.raises(ValueError, match="Illegal source trust transition"):
        record_source_event(db, "s2", "test_type", to_state, "attempt", observed_at=T + 1)


# ---------------------------------------------------------------------------
# Illegal transition must not mutate state
# ---------------------------------------------------------------------------

def test_illegal_transition_does_not_mutate_state():
    """H-5: State must remain unchanged after a rejected illegal transition."""
    db = _make_db()
    _seed(db, "s3", "approved", t=T)
    with pytest.raises(ValueError):
        record_source_event(db, "s3", "test_type", "candidate", "attempt", observed_at=T + 1)
    lc = get_source_lifecycle(db, "s3")
    assert lc["trust_state"] == "approved", (
        "H-5: State must still be 'approved' after rejected illegal transition"
    )


# ---------------------------------------------------------------------------
# Unknown event raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_event_raises():
    """H-5: Unknown event names must raise ValueError."""
    db = _make_db()
    with pytest.raises(ValueError, match="Unknown lifecycle event"):
        record_source_event(db, "s4", "test_type", "candidate", "bogus_event")


# ---------------------------------------------------------------------------
# Unknown trust_state raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_trust_state_raises():
    """H-5: Unknown trust_state values must raise ValueError."""
    db = _make_db()
    with pytest.raises(ValueError, match="Unknown source trust state"):
        record_source_event(db, "s5", "test_type", "phantom_state", "attempt")


# ---------------------------------------------------------------------------
# Consecutive failures increment correctly
# ---------------------------------------------------------------------------

def test_consecutive_failures_increment():
    """H-5: Failure events must increment consecutive_failures counter."""
    db = _make_db()
    _seed(db, "s6", "candidate", t=T)
    record_source_event(db, "s6", "test_type", "candidate", "failure", observed_at=T + 1)
    record_source_event(db, "s6", "test_type", "candidate", "failure", observed_at=T + 2)
    lc = get_source_lifecycle(db, "s6")
    assert lc["consecutive_failures"] == 2, (
        f"H-5: Expected 2 consecutive_failures, got {lc['consecutive_failures']}"
    )


# ---------------------------------------------------------------------------
# Success event resets consecutive_failures
# ---------------------------------------------------------------------------

def test_success_event_resets_consecutive_failures():
    """H-5: A 'valid' event must reset consecutive_failures to 0."""
    db = _make_db()
    _seed(db, "s7", "approved", t=T)
    record_source_event(db, "s7", "test_type", "approved", "failure", observed_at=T + 1)
    record_source_event(db, "s7", "test_type", "approved", "failure", observed_at=T + 2)
    record_source_event(db, "s7", "test_type", "approved", "valid",   observed_at=T + 3)
    lc = get_source_lifecycle(db, "s7")
    assert lc["consecutive_failures"] == 0, (
        f"H-5: consecutive_failures must reset to 0 after success, got {lc['consecutive_failures']}"
    )


# ---------------------------------------------------------------------------
# Stale event does not overwrite trust_state
# ---------------------------------------------------------------------------

def test_stale_event_does_not_overwrite_trust_state():
    """H-5: A stale event (older timestamp) must not downgrade/overwrite the trust_state."""
    db = _make_db()
    _seed(db, "s8", "candidate", t=T)
    record_source_event(db, "s8", "test_type", "approved", "valid", observed_at=T + 2)
    # Stale event arrives with quarantined at T + 1
    record_source_event(db, "s8", "test_type", "quarantined", "attempt", observed_at=T + 1)
    lc = get_source_lifecycle(db, "s8")
    assert lc["trust_state"] == "approved", "H-5: Stale quarantined event must not downgrade approved trust_state"
    assert lc["updated_at"] == T + 2, "updated_at must remain the latest timestamp"
