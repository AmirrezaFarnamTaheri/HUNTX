from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huntx.state import StateRepo


@pytest.mark.parametrize("days", [0, -1, True, 1.5, "30"])
def test_destructive_prune_requires_positive_integer_retention(days):
    db = MagicMock()
    repo = StateRepo(db)

    with pytest.raises(ValueError, match="positive integer"):
        repo.prune_old_data(days)  # type: ignore[arg-type]

    db.connect.assert_not_called()
