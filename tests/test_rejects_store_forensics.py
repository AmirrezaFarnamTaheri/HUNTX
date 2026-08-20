from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from huntx.store.rejects import RejectsStore


def test_same_moment_rejects_never_overwrite_each_other(tmp_path):
    store = RejectsStore(tmp_path)
    frozen = datetime(2026, 8, 19, 12, 0, 0, 123456, tzinfo=timezone.utc)

    with patch("huntx.store.rejects.datetime.datetime") as mocked_datetime:
        mocked_datetime.now.return_value = frozen
        first = store.save_reject("src/unsafe", "bad reason", b"first")
        second = store.save_reject("src/unsafe", "bad reason", b"second")

    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert first.parent == tmp_path
    assert second.parent == tmp_path
    assert "/" not in first.name


def test_reject_store_requires_bytes(tmp_path):
    store = RejectsStore(tmp_path)
    try:
        store.save_reject("src", "reason", "not-bytes")  # type: ignore[arg-type]
    except TypeError as exc:
        assert "must be bytes" in str(exc)
    else:
        raise AssertionError("RejectsStore accepted a non-bytes payload")
