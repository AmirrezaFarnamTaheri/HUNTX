import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_syncer() -> ModuleType:
    path = REPO_ROOT / "scripts" / "sync_generated_outputs_to_main.py"
    spec = importlib.util.spec_from_file_location("sync_generated_outputs_to_main_retry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNCER = _load_syncer()


def _write_snapshot(root: Path, output_value: str, manifest_value: str) -> None:
    (root / "outputs").mkdir(parents=True)
    (root / "outputs_dev").mkdir(parents=True)
    (root / "manifests").mkdir(parents=True)
    (root / "outputs" / "current.txt").write_text(output_value, encoding="utf-8")
    (root / "outputs_dev" / "_manifest.json").write_text(manifest_value, encoding="utf-8")
    (root / "manifests" / "main-sync-files.txt").write_text(
        "outputs/current.txt\noutputs_dev/_manifest.json\n",
        encoding="utf-8",
    )


class TestGeneratedMainSyncRetry(unittest.TestCase):
    def test_snapshot_can_be_reapplied_after_base_branch_advances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            snapshot_one = root / "snapshot-one"
            snapshot_two = root / "snapshot-two"
            (repo / "outputs").mkdir(parents=True)
            (repo / "outputs_dev").mkdir(parents=True)
            (repo / ".github").mkdir(parents=True)
            (repo / "docs").mkdir(parents=True)
            (repo / "outputs" / "verify_output.py").write_text("# helper\n", encoding="utf-8")
            inventory = repo / ".github" / "huntx-generated-files.txt"
            inventory.write_text("", encoding="utf-8")

            _write_snapshot(snapshot_one, "run-one\n", '{"one": 1}\n')
            SYNCER.sync_generated_outputs(snapshot_one, repo, inventory)

            (repo / "docs" / "concurrent-change.md").write_text(
                "unrelated branch advance\n",
                encoding="utf-8",
            )
            _write_snapshot(snapshot_two, "run-two\n", '{"one": 1, "two": 2}\n')
            copied, removed = SYNCER.sync_generated_outputs(snapshot_two, repo, inventory)

            self.assertEqual(copied, 2)
            self.assertEqual(removed, 0)
            self.assertEqual((repo / "outputs" / "current.txt").read_text(), "run-two\n")
            self.assertEqual(
                (repo / "outputs_dev" / "_manifest.json").read_text(),
                '{"one": 1, "two": 2}\n',
            )
            self.assertEqual(
                (repo / "docs" / "concurrent-change.md").read_text(),
                "unrelated branch advance\n",
            )
            self.assertTrue((repo / "outputs" / "verify_output.py").exists())


if __name__ == "__main__":
    unittest.main()
