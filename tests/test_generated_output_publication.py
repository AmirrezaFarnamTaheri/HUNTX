import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLER = _load_script(
    "assemble_generated_snapshot",
    REPO_ROOT / "scripts" / "assemble_generated_snapshot.py",
)
SYNCER = _load_script(
    "sync_generated_outputs_to_main",
    REPO_ROOT / "scripts" / "sync_generated_outputs_to_main.py",
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestGeneratedSnapshotAssembly(unittest.TestCase):
    def _build_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        checkpoint = root / "checkpoint" / "payload" / "data"
        outputs = checkpoint / "outputs"
        current_dev = checkpoint / "outputs_dev"
        outputs.mkdir(parents=True)
        current_dev.mkdir(parents=True)
        (outputs / "current.txt").write_text("current-run\n", encoding="utf-8")

        current_manifest = {
            "vless://shared.example:443?encryption=none#new-remark": 300,
            "vless://current.example:443?encryption=none": 200,
        }
        _write_json(current_dev / "_manifest.json", current_manifest)
        (current_dev / "proxies.txt").write_text("stale-current-render\n", encoding="utf-8")

        previous = root / "previous"
        previous_outputs = previous / "outputs"
        previous_dev = previous / "outputs_dev"
        previous_outputs.mkdir(parents=True)
        previous_dev.mkdir(parents=True)
        (previous_outputs / "previous.txt").write_text("must-not-carry\n", encoding="utf-8")
        previous_manifest = {
            "vless://previous.example:443?encryption=none": 100,
            "vless://shared.example:443?encryption=none#old-remark": 50,
        }
        _write_json(previous_dev / "_manifest.json", previous_manifest)

        dist = root / "dist"
        dist.mkdir()
        (dist / "catalog.json").write_text("{}\n", encoding="utf-8")
        logs = root / "logs"
        logs.mkdir()
        _write_json(logs / "run-summary.json", {"status": "partial"})
        return checkpoint, previous, dist, logs

    def test_outputs_are_per_run_and_outputs_dev_is_cumulative(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = self._build_fixture(root)
            destination = root / "snapshot"

            payload = ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=destination,
                run_id="123",
                run_attempt="2",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T17:24:27Z",
                previous_snapshot_root=previous,
            )

            self.assertEqual((destination / "outputs" / "current.txt").read_text(), "current-run\n")
            self.assertFalse((destination / "outputs" / "previous.txt").exists())

            manifest = json.loads((destination / "outputs_dev" / "_manifest.json").read_text())
            self.assertEqual(len(manifest), 3)
            self.assertEqual(manifest["vless://shared.example:443?encryption=none"], 50)
            self.assertEqual(payload["outputs_dev_previous_count"], 2)
            self.assertEqual(payload["outputs_dev_current_count"], 2)
            self.assertEqual(payload["outputs_dev_cumulative_count"], 3)

            rendered = json.loads((destination / "outputs_dev" / "proxies.json").read_text())
            self.assertEqual(rendered["_scope"], "all_time_cumulative")
            self.assertEqual(rendered["_count"], 3)
            encoded = (destination / "outputs_dev" / "proxies_b64sub.txt").read_text().strip()
            decoded_lines = base64.b64decode(encoded).decode("utf-8").splitlines()
            self.assertEqual(len(decoded_lines), 3)

            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            self.assertIn("outputs/current.txt", inventory)
            self.assertIn("outputs_dev/_manifest.json", inventory)
            self.assertIn("outputs_dev/proxies.txt", inventory)

    def test_republishing_the_same_run_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = self._build_fixture(root)
            destinations = [root / "snapshot-one", root / "snapshot-two"]

            for destination in destinations:
                ASSEMBLER.assemble_snapshot(
                    checkpoint_root=checkpoint,
                    dist_root=dist,
                    logs_root=logs,
                    destination=destination,
                    run_id="123",
                    run_attempt="2",
                    head_sha="abc123",
                    head_branch="main",
                    source_created_at="2026-07-30T17:24:27Z",
                    previous_snapshot_root=previous,
                )

            self.assertEqual(_tree_bytes(destinations[0]), _tree_bytes(destinations[1]))


class TestDashboardDataWiring(unittest.TestCase):
    """The published snapshot must carry fresh SPA data (catalog + artifacts).

    Regression context: the publication pipeline mirrored only outputs/ and
    outputs_dev/ to main, so docs/catalog.json and docs/artifacts/** stayed on
    their last manual commit while ingestion kept producing fresh releases.
    """

    def _dashboard_fixture(self, root: Path) -> Path:
        dashboard = root / "dashboard"
        (dashboard / "artifacts" / "release").mkdir(parents=True)
        (dashboard / "catalog.json").write_text('{"total_files": 1}\n', encoding="utf-8")
        (dashboard / "artifacts" / "release" / "manifest.json").write_text("{}\n", encoding="utf-8")
        return dashboard

    def test_dashboard_data_is_staged_into_snapshot_and_inventory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = (
                TestGeneratedSnapshotAssembly._build_fixture(self, root)
            )
            dashboard = self._dashboard_fixture(root)
            destination = root / "snapshot"

            payload = ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=destination,
                run_id="123",
                run_attempt="2",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T17:24:27Z",
                previous_snapshot_root=previous,
                dashboard_root=dashboard,
            )

            self.assertEqual(
                (destination / "docs" / "catalog.json").read_text(),
                '{"total_files": 1}\n',
            )
            self.assertTrue(
                (destination / "docs" / "artifacts" / "release" / "manifest.json").exists()
            )
            # The SPA's dev download links point at artifacts/dev/*; they must
            # carry the cumulative dev trio so downloads are never stale.
            for name in ("proxies.json", "proxies.txt", "proxies_b64sub.txt"):
                self.assertTrue(
                    (destination / "docs" / "artifacts" / "dev" / name).exists(),
                    f"missing dev artifact: {name}",
                )
            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            self.assertIn("docs/catalog.json", inventory)
            self.assertIn("docs/artifacts/release/manifest.json", inventory)
            self.assertIn("docs/artifacts/dev/proxies_b64sub.txt", inventory)
            self.assertGreaterEqual(payload["dashboard_file_count"], 5)

    def test_assembly_without_dashboard_root_stays_back_compatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = (
                TestGeneratedSnapshotAssembly._build_fixture(self, root)
            )
            destination = root / "snapshot"

            ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=destination,
                run_id="123",
                run_attempt="2",
                head_sha="abc123",
                head_branch="main",
                source_created_at="2026-07-30T17:24:27Z",
                previous_snapshot_root=previous,
            )

            self.assertFalse((destination / "docs").exists())
            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            self.assertFalse(any(line.startswith("docs/") for line in inventory))


class TestGeneratedMainSync(unittest.TestCase):
    def test_sync_removes_only_managed_stale_files_and_preserves_helpers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = root / "snapshot"
            repo = root / "repo"
            (snapshot / "outputs").mkdir(parents=True)
            (snapshot / "outputs_dev").mkdir(parents=True)
            (snapshot / "manifests").mkdir(parents=True)
            (repo / "outputs").mkdir(parents=True)
            (repo / "outputs_dev").mkdir(parents=True)
            (repo / ".github").mkdir(parents=True)

            (snapshot / "outputs" / "current.txt").write_text("new\n", encoding="utf-8")
            (snapshot / "outputs_dev" / "_manifest.json").write_text("{}\n", encoding="utf-8")
            (snapshot / "manifests" / "main-sync-files.txt").write_text(
                "outputs/current.txt\noutputs_dev/_manifest.json\n",
                encoding="utf-8",
            )

            (repo / "outputs" / "stale.txt").write_text("stale\n", encoding="utf-8")
            (repo / "outputs" / "verify_output.py").write_text("# helper\n", encoding="utf-8")
            inventory = repo / ".github" / "huntx-generated-files.txt"
            inventory.write_text("outputs/stale.txt\n", encoding="utf-8")

            copied, removed = SYNCER.sync_generated_outputs(
                snapshot_root=snapshot,
                repo_root=repo,
                inventory_path=inventory,
            )

            self.assertEqual(copied, 2)
            self.assertEqual(removed, 1)
            self.assertFalse((repo / "outputs" / "stale.txt").exists())
            self.assertEqual((repo / "outputs" / "current.txt").read_text(), "new\n")
            self.assertTrue((repo / "outputs" / "verify_output.py").exists())
            self.assertEqual(
                inventory.read_text().splitlines(),
                ["outputs/current.txt", "outputs_dev/_manifest.json"],
            )

    def test_sync_rejects_inventory_path_traversal_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = root / "snapshot"
            repo = root / "repo"
            (snapshot / "manifests").mkdir(parents=True)
            repo.mkdir()
            (snapshot / "manifests" / "main-sync-files.txt").write_text(
                "outputs/../escape.txt\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                SYNCER.sync_generated_outputs(
                    snapshot_root=snapshot,
                    repo_root=repo,
                    inventory_path=Path(".github/huntx-generated-files.txt"),
                )
            self.assertFalse((root / "escape.txt").exists())

    def test_sync_copies_dashboard_data_and_prunes_stale_docs_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = root / "snapshot"
            repo = root / "repo"

            fresh_catalog = snapshot / "docs" / "catalog.json"
            fresh_release = snapshot / "docs" / "artifacts" / "release" / "manifest.json"
            fresh_dev = snapshot / "docs" / "artifacts" / "dev" / "proxies.json"
            fresh_dev_b64 = snapshot / "docs" / "artifacts" / "dev" / "proxies_b64sub.txt"
            for path in (fresh_catalog, fresh_release, fresh_dev, fresh_dev_b64):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            (snapshot / "outputs").mkdir(parents=True)
            (snapshot / "outputs" / "current.txt").write_text("current-run\n", encoding="utf-8")
            (snapshot / "manifests").mkdir(parents=True)
            new_inventory = [
                "outputs/current.txt",
                "docs/catalog.json",
                "docs/artifacts/release/manifest.json",
                "docs/artifacts/dev/proxies_b64sub.txt",
            ]
            (snapshot / "manifests" / "main-sync-files.txt").write_text(
                "\n".join(new_inventory) + "\n",
                encoding="utf-8",
            )

            (repo / "outputs").mkdir(parents=True)
            (repo / "outputs" / "stale.txt").write_text("stale\n", encoding="utf-8")
            (repo / ".github").mkdir(parents=True, exist_ok=True)
            stale_docs_dev = repo / "docs" / "artifacts" / "dev" / "proxies.txt"
            stale_docs_dev.parent.mkdir(parents=True)
            stale_docs_dev.write_text("stale\n", encoding="utf-8")
            helper = repo / "docs" / "index.html"
            helper.write_text("<html>hand-maintained shell</html>\n", encoding="utf-8")
            inventory = repo / ".github" / "huntx-generated-files.txt"
            inventory.write_text(
                "outputs/stale.txt\ndocs/artifacts/dev/proxies.txt\n",
                encoding="utf-8",
            )

            copied, removed = SYNCER.sync_generated_outputs(
                snapshot_root=snapshot,
                repo_root=repo,
                inventory_path=inventory,
            )

            self.assertEqual(copied, 4)
            self.assertEqual(removed, 2)
            self.assertTrue((repo / "docs" / "catalog.json").exists())
            self.assertTrue((repo / "docs" / "artifacts" / "release" / "manifest.json").exists())
            self.assertFalse(stale_docs_dev.exists())
            self.assertTrue(helper.exists(), "hand-maintained shell must not be touched")

    def test_sync_rejects_unmanaged_docs_paths(self):
        for value in (
            "docs/assets/js/app.js",
            "docs/assets/css/site.css",
            "docs/secrets.txt",
            "doc/catalog.json",
        ):
            with self.assertRaises(ValueError):
                SYNCER.parse_managed_path(value)


if __name__ == "__main__":
    unittest.main()
