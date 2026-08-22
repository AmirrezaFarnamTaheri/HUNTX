from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from huntx.cli.commands.maintenance import cleanup_targets
from huntx.store import paths


@contextmanager
def _temporary_runtime_paths(data_dir: Path, db_path: Path):
    original = paths.current_paths()
    paths.set_paths(str(data_dir), str(db_path))
    try:
        yield
    finally:
        paths.set_paths(str(original.data_dir), str(original.state_db_path))


def test_cleanup_targets_include_live_artifact_store_directories(tmp_path):
    data_dir = tmp_path / "data"
    db_path = data_dir / "state" / "state.db"

    with _temporary_runtime_paths(data_dir, db_path):
        targets = {path.resolve() for path in cleanup_targets(db_path)}

        assert (data_dir / "dist").resolve() in targets
        assert (data_dir / "archive").resolve() in targets
        assert paths.OUTPUT_DIR.resolve() in targets
        assert paths.DEV_OUTPUT_DIR.resolve() in targets
        assert paths.RAW_STORE_DIR.resolve() in targets
        assert paths.REJECTS_DIR.resolve() in targets
        assert db_path.resolve() in targets
        assert paths.STATE_DIR.resolve() in targets


def test_cleanup_targets_are_deduplicated(tmp_path):
    data_dir = tmp_path / "data"
    db_path = data_dir / "state" / "state.db"

    with _temporary_runtime_paths(data_dir, db_path):
        targets = cleanup_targets(db_path)
        resolved = [Path(path).resolve() for path in targets]
        assert len(resolved) == len(set(resolved))
