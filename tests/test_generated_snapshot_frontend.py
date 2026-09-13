import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontend_refresh_uses_final_staged_catalog(tmp_path: Path) -> None:
    assembler = _load_assembler()
    docs = tmp_path / "docs"
    data_dir = docs / "assets" / "js"
    data_dir.mkdir(parents=True)
    (data_dir / "data.js").write_text(
        'window.HUNTX_DATA = {"total_production_nodes": 7};\n',
        encoding="utf-8",
    )
    (docs / "catalog.json").write_text(
        json.dumps({"files": [{"filename": f"artifact-{index}"} for index in range(18)]}),
        encoding="utf-8",
    )

    assembler._refresh_frontend_index(tmp_path)

    rendered = (docs / "index.html").read_text(encoding="utf-8")
    assert re.search(r'id="tab-proxies-count-badge"[^>]*>7</span>', rendered)
    assert re.search(r'id="tab-artifacts-count-badge"[^>]*>18</span>', rendered)
