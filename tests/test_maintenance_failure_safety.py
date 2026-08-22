from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from huntx.cli.commands import maintenance


def test_clean_aborts_before_deletion_when_user_preservation_fails(tmp_path):
    db_path = tmp_path / "state.db"
    db_path.write_bytes(b"not-a-real-db")

    with (
        patch.object(maintenance.paths, "STATE_DB_PATH", db_path),
        patch.object(maintenance, "cleanup_targets", return_value=[db_path]),
        patch.object(
            maintenance,
            "backup_bot_users",
            side_effect=RuntimeError("preservation failed"),
        ),
        patch.object(maintenance, "_remove_targets") as remove,
    ):
        with pytest.raises(RuntimeError, match="preservation failed"):
            maintenance.clean_command(SimpleNamespace(yes=True))

    remove.assert_not_called()
    assert db_path.exists()


def test_reset_aborts_before_deletion_when_full_backup_fails(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "state.db"
    db_path.write_bytes(b"state")

    with (
        patch.object(maintenance.paths, "DATA_DIR", data_dir),
        patch.object(maintenance.paths, "STATE_DB_PATH", db_path),
        patch.object(maintenance, "cleanup_targets", return_value=[db_path]),
        patch.object(maintenance.shutil, "copy2", side_effect=OSError("disk full")),
        patch.object(maintenance, "backup_bot_users") as backup_users,
        patch.object(maintenance, "_remove_targets") as remove,
    ):
        with pytest.raises(RuntimeError, match="reset backup"):
            maintenance.reset_command(SimpleNamespace(yes=True))

    backup_users.assert_not_called()
    remove.assert_not_called()
    assert db_path.exists()


def test_clean_restores_users_before_reporting_partial_deletion_failure(tmp_path):
    db_path = tmp_path / "state.db"
    db_path.write_bytes(b"state")
    users = [{"user_id": "1", "chat_id": "1", "registered_at": 1.0}]

    with (
        patch.object(maintenance.paths, "STATE_DB_PATH", db_path),
        patch.object(maintenance, "cleanup_targets", return_value=[db_path]),
        patch.object(maintenance, "backup_bot_users", return_value=users),
        patch.object(maintenance, "_remove_targets", return_value=(0, ["state.db: OSError"])),
        patch.object(maintenance.paths, "ensure_dirs"),
        patch.object(maintenance, "restore_bot_users") as restore,
    ):
        with pytest.raises(RuntimeError, match="Cleanup incomplete"):
            maintenance.clean_command(SimpleNamespace(yes=True))

    restore.assert_called_once_with(db_path, users)
