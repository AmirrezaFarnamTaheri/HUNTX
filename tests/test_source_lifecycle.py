import pytest

from huntx.state.db import open_db
from huntx.state.lifecycle import get_source_lifecycle, record_source_event


def test_lifecycle_timestamps_and_failure_sequence_are_monotonic(tmp_path):
    db = open_db(tmp_path / "state.db")
    record_source_event(
        db,
        "source",
        "telegram",
        "approved",
        "failure",
        observed_at=20,
        error_code="NEW_FAILURE",
    )
    record_source_event(
        db,
        "source",
        "telegram",
        "approved",
        "transport_success",
        observed_at=10,
    )

    lifecycle = get_source_lifecycle(db, "source")
    assert lifecycle["updated_at"] == 20
    assert lifecycle["last_transport_success_at"] == 10
    assert lifecycle["consecutive_failures"] == 1
    assert lifecycle["last_error_code"] == "NEW_FAILURE"


def test_retired_source_cannot_regress_to_active_state(tmp_path):
    db = open_db(tmp_path / "state.db")
    record_source_event(
        db,
        "source",
        "telegram",
        "retired",
        "attempt",
        observed_at=10,
    )

    with pytest.raises(ValueError, match="retired -> approved"):
        record_source_event(
            db,
            "source",
            "telegram",
            "approved",
            "attempt",
            observed_at=20,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_lifecycle_rejects_nonfinite_timestamps(tmp_path, value):
    db = open_db(tmp_path / "state.db")
    with pytest.raises(ValueError, match="finite"):
        record_source_event(
            db,
            "source",
            "telegram",
            "candidate",
            "attempt",
            observed_at=value,
        )
