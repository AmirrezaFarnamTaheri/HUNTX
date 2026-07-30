import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_validation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLER = _load_assembler()


class TestGeneratedManifestValidation(unittest.TestCase):
    def test_malformed_previous_manifest_fails_with_source_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint = root / "checkpoint" / "data"
            outputs = checkpoint / "outputs"
            current_dev = checkpoint / "outputs_dev"
            outputs.mkdir(parents=True)
            current_dev.mkdir(parents=True)
            (outputs / "current.txt").write_text("current\n", encoding="utf-8")
            (current_dev / "_manifest.json").write_text(
                json.dumps({"vless://current.example:443?encryption=none": 200}),
                encoding="utf-8",
            )

            previous_manifest = root / "previous" / "outputs_dev" / "_manifest.json"
            previous_manifest.parent.mkdir(parents=True)
            previous_manifest.write_text("[]\n", encoding="utf-8")
            dist = root / "dist"
            logs = root / "logs"
            dist.mkdir()
            logs.mkdir()
            (dist / "catalog.json").write_text("{}\n", encoding="utf-8")
            destination = root / "snapshot"

            with self.assertRaisesRegex(ValueError, str(previous_manifest)):
                ASSEMBLER.assemble_snapshot(
                    checkpoint_root=checkpoint,
                    dist_root=dist,
                    logs_root=logs,
                    destination=destination,
                    run_id="123",
                    run_attempt="1",
                    head_sha="abc123",
                    head_branch="main",
                    source_created_at="2026-07-30T17:24:27Z",
                    previous_snapshot_root=root / "previous",
                )

            self.assertFalse((destination / "manifests" / "publication.json").exists())


if __name__ == "__main__":
    unittest.main()
