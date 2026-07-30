import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_repository", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restored_repository_legacy_snapshot_recovers_large_cumulative_history():
    assembler = _load_assembler()
    recovered = assembler.load_legacy_dev_identities(REPO_ROOT / "outputs_dev")

    assert len(recovered) >= 100_000
    assert all(isinstance(uri, str) and "://" in uri for uri in recovered)
