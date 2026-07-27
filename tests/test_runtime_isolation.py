from huntx.formats.registry import FormatRegistry
from huntx.store import paths


class _Handler:
    def __init__(self, format_id: str):
        self.format_id = format_id


def test_format_registries_are_instance_scoped():
    first = FormatRegistry()
    second = FormatRegistry()
    first.register(_Handler("only-first"))

    assert first.get("only-first") is not None
    assert second.get("only-first") is None


def test_runtime_paths_snapshot_is_immutable_and_stable(monkeypatch, tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    paths.set_paths(str(first_root), str(first_root / "state.db"))
    snapshot = paths.current_paths()

    paths.set_paths(str(second_root), str(second_root / "state.db"))

    assert snapshot.data_dir == first_root.resolve()
    assert snapshot.output_dir == (first_root / "outputs").resolve()
    assert snapshot.state_db_path == (first_root / "state.db").resolve()
    assert paths.current_paths().data_dir == second_root.resolve()
