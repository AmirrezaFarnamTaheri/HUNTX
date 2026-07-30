import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_legacy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLER = _load_assembler()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestLegacyDevBootstrap(unittest.TestCase):
    def test_blank_manifest_recovers_rendered_history_without_overwriting_known_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "legacy"
            legacy.mkdir()
            (legacy / "_manifest.json").write_text("", encoding="utf-8")
            (legacy / "proxies.txt").write_text(
                "# legacy cumulative list\n\n"
                "vless://legacy.example:443?encryption=none#old-label\n"
                "vless://shared.example:443?encryption=none#legacy-label\n",
                encoding="utf-8",
            )

            previous = root / "previous"
            _write_json(
                previous / "outputs_dev" / "_manifest.json",
                {"vless://shared.example:443?encryption=none": 100},
            )
            checkpoint = root / "checkpoint" / "data"
            (checkpoint / "outputs").mkdir(parents=True)
            (checkpoint / "outputs" / "current.txt").write_text("current\n", encoding="utf-8")
            _write_json(
                checkpoint / "outputs_dev" / "_manifest.json",
                {"vless://current.example:443?encryption=none": 200},
            )
            dist = root / "dist"
            logs = root / "logs"
            dist.mkdir()
            logs.mkdir()
            (dist / "catalog.json").write_text("{}\n", encoding="utf-8")

            payload = ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=root / "snapshot",
                run_id="123",
                run_attempt="1",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T18:00:00Z",
                previous_snapshot_root=previous,
                legacy_dev_root=legacy,
            )

            manifest = json.loads((root / "snapshot" / "outputs_dev" / "_manifest.json").read_text())
            self.assertEqual(len(manifest), 3)
            self.assertEqual(manifest["vless://legacy.example:443?encryption=none"], 0)
            self.assertEqual(manifest["vless://shared.example:443?encryption=none"], 100)
            self.assertEqual(manifest["vless://current.example:443?encryption=none"], 200)
            self.assertEqual(payload["outputs_dev_legacy_count"], 2)
            self.assertEqual(payload["outputs_dev_cumulative_count"], 3)

    def test_json_and_base64_legacy_layouts_are_recoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_dev = root / "json-dev"
            json_dev.mkdir()
            _write_json(
                json_dev / "proxies.json",
                {
                    "proxies": [
                        {
                            "uri": "vless://json.example:443?encryption=none#label",
                            "first_seen": 25,
                        }
                    ]
                },
            )
            json_manifest = ASSEMBLER.load_legacy_dev_identities(json_dev)
            self.assertEqual(json_manifest, {"vless://json.example:443?encryption=none": 25})

            b64_dev = root / "b64-dev"
            b64_dev.mkdir()
            payload = base64.b64encode(
                b"vless://base64.example:443?encryption=none#label\n"
            ).decode("ascii")
            (b64_dev / "proxies_b64sub.txt").write_text(payload + "\n", encoding="utf-8")
            b64_manifest = ASSEMBLER.load_legacy_dev_identities(b64_dev)
            self.assertEqual(b64_manifest, {"vless://base64.example:443?encryption=none": 0})

    def test_nonempty_unrecoverable_legacy_layout_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy = Path(temp_dir)
            (legacy / "proxies.txt").write_text("not-a-proxy\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "could not be recovered"):
                ASSEMBLER.load_legacy_dev_identities(legacy)


def test_workflow_passes_default_branch_legacy_output_to_assembler():
    workflow = Path(".github/workflows/publish-generated-outputs.yml").read_text()
    assert 'LEGACY_DEV_ROOT: ${{ github.workspace }}/outputs_dev' in workflow
    assert '--legacy-dev-root "$LEGACY_DEV_ROOT"' in workflow


if __name__ == "__main__":
    unittest.main()
