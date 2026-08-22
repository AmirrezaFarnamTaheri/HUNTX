from __future__ import annotations

import pytest

from huntx.core.locks import acquire_lock


def test_acquire_lock_does_not_mask_protected_operation_oserror(tmp_path):
    lock_path = tmp_path / "huntx.lock"

    with pytest.raises(OSError, match="real downstream failure"):
        with acquire_lock(lock_path):
            raise OSError("real downstream failure")
