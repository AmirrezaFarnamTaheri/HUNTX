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
            self.assertNotIn("outputs_dev/_manifest.json", inventory)
            self.assertIn("outputs_dev/_manifest.json.gz.index.json", inventory)
            self.assertTrue(any(path.startswith("outputs_dev/_manifest.json.gz.part") for path in inventory))
            self.assertNotIn("outputs_dev/proxies.txt", inventory)
            self.assertTrue((destination / "outputs_dev" / "proxies.txt").is_file())

    def test_compressed_cumulative_manifest_loads_from_sharded_git_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dev_dir = Path(temp_dir) / "outputs_dev"
            dev_dir.mkdir()
            expected = {
                "vless://first.example:443?encryption=none": 100,
                "vmess://eyJhZGQiOiJzZWNvbmQuZXhhbXBsZSJ9": 200,
            }
            chunk_size = ASSEMBLER._MANIFEST_CHUNK_BYTES
            ASSEMBLER._MANIFEST_CHUNK_BYTES = 32
            try:
                ASSEMBLER.write_compressed_dev_manifest(dev_dir, expected)
            finally:
                ASSEMBLER._MANIFEST_CHUNK_BYTES = chunk_size

            self.assertEqual(
                ASSEMBLER.load_dev_manifest(dev_dir / "_manifest.json"),
                expected,
            )
            self.assertTrue((dev_dir / "_manifest.json.gz.index.json").is_file())
            self.assertGreater(len(list(dev_dir.glob("_manifest.json.gz.part*"))), 1)

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
        release_entry = {
            "filename": "all_sources.conf_lines",
            "path": "artifacts/release/all_sources.conf_lines",
            "size": 10,
            "sha256": "a" * 64,
        }
        catalog = {"total_files": 1, "total_size": 10, "files": [release_entry]}
        (dashboard / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
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

            staged_catalog = json.loads((destination / "docs" / "catalog.json").read_text())
            dev_entries = [f for f in staged_catalog["files"] if f.get("section") == "dev"]
            assert [f["filename"] for f in dev_entries] == ["proxies.json"]
            assert staged_catalog["total_files"] == 2
            assert dev_entries[0]["path"] == "artifacts/dev/proxies.json"
            assert len(dev_entries[0]["sha256"]) == 64
            self.assertTrue(
                (destination / "docs" / "artifacts" / "release" / "manifest.json").exists()
            )
            # Compatibility variants remain deployed for direct URLs, but only
            # proxies.json is advertised as the final cumulative product.
            for name in ("proxies.json", "proxies.txt", "proxies_b64sub.txt"):
                self.assertTrue(
                    (destination / "docs" / "artifacts" / "dev" / name).exists(),
                    f"missing dev artifact: {name}",
                )
            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            self.assertIn("docs/catalog.json", inventory)
            self.assertIn("docs/artifacts/release/manifest.json", inventory)
            self.assertNotIn("docs/artifacts/dev/proxies_b64sub.txt", inventory)
            self.assertTrue((destination / "docs" / "artifacts" / "dev" / "proxies_b64sub.txt").is_file())
            self.assertGreaterEqual(payload["dashboard_file_count"], 5)

    def test_republishing_old_run_does_not_restore_dotted_derivatives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = TestGeneratedSnapshotAssembly._build_fixture(self, root)
            dashboard = self._dashboard_fixture(root)
            legacy = "all_sources.npvt.nekobox.json"
            canonical = "all_sources_npvt_nekobox.json"
            for directory in (checkpoint / "outputs", dashboard / "artifacts" / "release"):
                (directory / legacy).write_text('{"outbounds": []}', encoding="utf-8")
                (directory / canonical).write_text('[{"type": "vless", "tag": "node"}]', encoding="utf-8")
            _write_json(dashboard / "artifacts" / "release" / "manifest.json", {
                "schema_version": 1,
                "artifact_count": 2,
                "artifacts": [{"path": legacy}, {"path": canonical}],
            })
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
                dashboard_root=dashboard,
            )

            assert not (destination / "outputs" / legacy).exists()
            assert not (destination / "docs" / "artifacts" / "release" / legacy).exists()
            assert (destination / "outputs" / canonical).exists()
            manifest = json.loads((destination / "docs" / "artifacts" / "release" / "manifest.json").read_text())
            assert manifest["artifact_count"] == 1
            assert [item["path"] for item in manifest["artifacts"]] == [canonical]
            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            assert not any(path.endswith(legacy) for path in inventory)

    def test_retired_bundle_is_never_staged_from_the_shell(self):
        """The standalone bundle.js is retired: native modules are the
        production entrypoint. A stray bundle in the shell must not land in the
        generated-only snapshot or the main-sync inventory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint, previous, dist, logs = (
                TestGeneratedSnapshotAssembly._build_fixture(self, root)
            )
            dashboard = self._dashboard_fixture(root)
            shell = root / "shell"
            (shell / "assets" / "js").mkdir(parents=True)
            (shell / "index.html").write_text("<html></html>", encoding="utf-8")
            (shell / "assets" / "js" / "data.js").write_text(
                "window.HUNTX_DATA = {};", encoding="utf-8")
            # Simulate a stale local checkout that still holds the retired bundle.
            (shell / "assets" / "js" / "bundle.js").write_text(
                "// retired", encoding="utf-8")
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
                dashboard_root=dashboard,
                shell_root=shell,
            )

            self.assertTrue((destination / "docs" / "index.html").exists())
            self.assertTrue((destination / "docs" / "assets" / "js" / "data.js").exists())
            self.assertFalse(
                (destination / "docs" / "assets" / "js" / "bundle.js").exists(),
                "retired bundle.js must never be staged into the snapshot",
            )
            inventory = (destination / "manifests" / "main-sync-files.txt").read_text().splitlines()
            self.assertNotIn("docs/assets/js/bundle.js", inventory)
            self.assertIn("docs/assets/js/data.js", inventory)

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
    def test_catalog_omits_files_outside_the_generated_inventory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            catalog_path = repo / "docs" / "catalog.json"
            catalog_path.parent.mkdir(parents=True)
            _write_json(catalog_path, {
                "files": [
                    {"path": "artifacts/dev/proxies.json", "size": 120},
                    {"path": "artifacts/release/current.json", "size": 50},
                ],
                "total_files": 2,
                "total_size": 170,
                "total_size_str": "170 B",
            })
            data_path = repo / "docs" / "assets" / "js" / "data.js"
            data_path.parent.mkdir(parents=True)
            data_path.write_text(
                'export const FALLBACK_CATALOG = '
                + json.dumps({"files": [
                    {"path": "artifacts/dev/proxies.json", "size": 120},
                    {"path": "artifacts/release/current.json", "size": 50},
                ]})
                + ";\n",
                encoding="utf-8",
            )

            changed = SYNCER.prune_catalog_to_inventory(
                repo,
                [Path("docs/catalog.json"), Path("docs/artifacts/release/current.json")],
            )

            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertTrue(changed)
            self.assertEqual([entry["path"] for entry in catalog["files"]], ["artifacts/release/current.json"])
            self.assertEqual(catalog["total_files"], 1)
            self.assertEqual(catalog["total_size"], 50)
            fallback = data_path.read_text(encoding="utf-8")
            self.assertNotIn("artifacts/dev/proxies.json", fallback)
            self.assertIn('"total_files":1', fallback)

    def test_catalog_prune_syncs_a_stale_fallback_when_catalog_is_current(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            docs = repo / "docs"
            catalog_path = docs / "catalog.json"
            data_path = docs / "assets" / "js" / "data.js"
            data_path.parent.mkdir(parents=True)
            current_catalog = {
                "files": [{"path": "artifacts/release/current.json", "size": 50}],
                "total_files": 1,
                "total_size": 50,
                "total_size_str": "50 B",
            }
            _write_json(catalog_path, current_catalog)
            data_path.write_text(
                'export const FALLBACK_CATALOG = '
                + json.dumps({
                    **current_catalog,
                    "files": current_catalog["files"]
                    + [{"path": "artifacts/dev/proxies.json", "size": 120}],
                })
                + ";\n",
                encoding="utf-8",
            )

            changed = SYNCER.prune_catalog_to_inventory(
                repo,
                [Path("docs/catalog.json"), Path("docs/artifacts/release/current.json")],
            )

            self.assertTrue(changed)
            fallback = data_path.read_text(encoding="utf-8")
            self.assertNotIn("artifacts/dev/proxies.json", fallback)
            self.assertIn('"total_files":1', fallback)

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

    def test_sync_rejects_the_retired_bundle_path(self):
        """bundle.js is retired: it must not be a machine-managed path, or a
        stray bundle could be mirrored into main over the native modules."""
        with self.assertRaises(ValueError):
            SYNCER.parse_managed_path("docs/assets/js/bundle.js")

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


def test_publisher_rejects_degraded_producer_before_downloads():
    """A successful huntx-production run without its release artifacts must fail
    the publisher's source resolution, not surface as a missing-artifact error."""
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-generated-outputs.yml").read_text(encoding="utf-8")
    resolution = workflow.split("Resolve and validate source run", 1)[1].split("- name: Checkout publisher control plane", 1)[0]
    assert "listWorkflowRunArtifacts" in resolution
    assert "huntx-output-" in resolution
    fail_index = resolution.index("core.setFailed")
    assert fail_index < resolution.index("core.setOutput('run_id'")


def _resolution_script() -> str:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-generated-outputs.yml").read_text(encoding="utf-8")
    return workflow.split("Resolve and validate source run", 1)[1].split("- name: Checkout publisher control plane", 1)[0]


def test_publisher_treats_an_intentional_no_release_as_a_clean_no_op():
    """A producer that deliberately withholds a release must keep the current
    deployment green instead of failing the downstream publisher."""
    resolution = _resolution_script()
    assert "noReleaseVerdictName" in resolution
    assert "huntx-no-release-" in resolution
    workflow_run_branch = resolution.split("if (context.eventName === 'workflow_run')", 1)[1]
    assert "intentional" in workflow_run_branch
    notice = workflow_run_branch.index("core.notice(")
    failed = workflow_run_branch.index("core.setFailed(")
    # The intentional path skips with a notice before the anomalous path fails.
    assert notice < failed


def test_publisher_only_downloads_after_the_readiness_gate():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-generated-outputs.yml").read_text(encoding="utf-8")
    body = workflow.split("- name: Checkout publisher control plane", 1)[1]
    # A clean skip must not reach the receipt verifier or diagnostics download.
    assert "if: steps.source.outputs.ready == 'true'" in body
    verify = workflow.split("- name: Verify current release eligibility", 1)[1]
    verify = verify.split("- name: Build verified dashboard data", 1)[0]
    assert "if: steps.source.outputs.ready == 'true'" in verify


def test_publisher_skips_legacy_runs_without_a_receipt_instead_of_failing():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-generated-outputs.yml").read_text(encoding="utf-8")
    verify = workflow.split("- name: Verify current release eligibility", 1)[1]
    verify = verify.split("- name: Build verified dashboard data", 1)[0]
    assert "release-receipt.json" in verify
    assert "predates the release-receipt protocol" in verify


def test_producer_publishes_a_no_release_verdict_when_packaging_is_withheld():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "huntx.yml").read_text(encoding="utf-8")
    step = workflow.split("- name: Record explicit no-release verdict", 1)[1]
    step = step.split("- name: Upload checkpoint handoff", 1)[0]
    assert "steps.package.outputs.ready != 'true'" in step
    assert "huntx-no-release-${{ github.run_id }}-${{ github.run_attempt }}" in step
