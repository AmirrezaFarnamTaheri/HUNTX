"""Runtime path defaults must follow argparse's last-option-wins rule."""

from pathlib import Path

import pytest

from huntx.cli.hardened_main import _inject_runtime_path_arguments


@pytest.mark.parametrize(
    "options",
    [
        ["--data-dir", "first", "--data-dir", "second"],
        ["--data-dir=first", "--data-dir=second"],
        ["--data-dir", "first", "--data-dir=second"],
    ],
)
def test_default_database_uses_last_explicit_data_directory(monkeypatch, options):
    monkeypatch.delenv("HUNTX_STATE_DB_PATH", raising=False)
    monkeypatch.setenv("HUNTX_DATA_DIR", "environment")

    resolved = _inject_runtime_path_arguments(["huntx", *options, "bot"])

    assert resolved[resolved.index("--db-path") + 1] == str(Path("second") / "state" / "state.db")
    assert resolved[3:] == [*options, "bot"]


def test_explicit_database_still_overrides_data_directory(monkeypatch):
    monkeypatch.setenv("HUNTX_STATE_DB_PATH", "environment.db")
    argv = ["huntx", "--data-dir", "first", "--data-dir", "second", "--db-path", "chosen.db", "bot"]
    assert _inject_runtime_path_arguments(argv) == argv
