import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_empty_dev", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLER = _load_assembler()


class TestEmptyCurrentDevPublication(unittest.TestCase):
    def _base_paths(self, root: Path) -> tuple[Path, Path, Path]:
        checkpoint = root / "checkpoint" / "data"
        outputs = checkpoint / "outputs"
        outputs.mkdir(parents=True)
        (outputs / "current.txt").write_text("current\n", encoding="utf-8")
        dist = root / "dist"
        logs = root / "logs"
        dist.mkdir()
        logs.mkdir()
        (dist / "catalog.json").write_text("{}\n", encoding="utf-8")
        return checkpoint, dist, logs

    def test_no_new_dev_records_preserves_previous_cumulative_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, dist, logs = self._base_paths(root)
            previous_manifest = root / "previous" / "outputs_dev" / "_manifest.json"
            previous_manifest.parent.mkdir(parents=True)
            previous_manifest.write_text(
                json.dumps({"vless://previous.example:443?encryption=none": 100}),
                encoding="utf-8",
            )

            payload = ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=root / "snapshot",
                run_id="123",
                run_attempt="1",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T17:24:27Z",
                previous_snapshot_root=root / "previous",
            )

            manifest = json.loads((root / "snapshot" / "outputs_dev" / "_manifest.json").read_text())
            self.assertEqual(manifest, {"vless://previous.example:443?encryption=none": 100})
            self.assertEqual(payload["outputs_dev_current_count"], 0)
            self.assertEqual(payload["outputs_dev_cumulative_count"], 1)

    def test_first_publication_without_dev_records_writes_empty_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, dist, logs = self._base_paths(root)

            payload = ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=root / "snapshot",
                run_id="123",
                run_attempt="1",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T17:24:27Z",
            )

            manifest = json.loads((root / "snapshot" / "outputs_dev" / "_manifest.json").read_text())
            rendered = json.loads((root / "snapshot" / "outputs_dev" / "proxies.json").read_text())
            self.assertEqual(manifest, {})
            self.assertEqual(rendered["_count"], 0)
            self.assertEqual(payload["outputs_dev_cumulative_count"], 0)


if __name__ == "__main__":
    unittest.main()
