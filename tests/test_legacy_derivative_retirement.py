"""Legacy derivative retirement must follow the naming rule, not a copy of it.

``retire_legacy_derivatives`` used to rebuild the canonical filename inline as
``{route}_{fmt}_{suffix}``. After the published names dropped the format
segment that spelling no longer exists, so the function found the legacy dotted
file, concluded no replacement was present, and left both in every snapshot
forever - a silent leak that no existing test covered, because they all use a
freshly built directory with no legacy files in it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_assembler():
    spec = importlib.util.spec_from_file_location(
        "assemble_generated_snapshot_probe", ROOT / "scripts" / "assemble_generated_snapshot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = [
    "all_sources.npvt.singbox.json",
    "all_sources.npvt.decoded.json",
    "all_sources.npvtsub.singbox.json",
]
CANONICAL = [
    "all_sources_singbox.json",
    "all_sources.json",
    "all_sources_sub_singbox.json",
]


def _seed(directory: Path, names: list[str]) -> None:
    for name in names:
        (directory / name).write_text("payload", encoding="utf-8")


def test_legacy_derivatives_are_retired_once_the_canonical_replacement_exists(tmp_path):
    module = _load_assembler()
    _seed(tmp_path, LEGACY + CANONICAL)

    removed = module.retire_legacy_derivatives(tmp_path)

    assert "all_sources.npvt.singbox.json" in removed
    assert "all_sources.npvt.decoded.json" in removed
    assert "all_sources.npvtsub.singbox.json" in removed
    for name in CANONICAL:
        assert (tmp_path / name).exists(), f"{name} was deleted"
    for name in removed:
        assert not (tmp_path / name).exists()


def test_nothing_is_retired_while_the_canonical_replacement_is_absent(tmp_path):
    """Retiring without a replacement would drop a product that has no other copy."""
    module = _load_assembler()
    _seed(tmp_path, LEGACY)

    removed = module.retire_legacy_derivatives(tmp_path)

    assert removed == set()
    for name in LEGACY:
        assert (tmp_path / name).exists(), f"{name} was deleted with no replacement"


def test_a_frozen_alias_is_never_deleted_by_its_own_canonical_name(tmp_path):
    """all_sources.npvt.raw.txt is a frozen alias, and is its own canonical name."""
    module = _load_assembler()
    _seed(tmp_path, ["all_sources.npvt.raw.txt"])

    removed = module.retire_legacy_derivatives(tmp_path)

    assert "all_sources.npvt.raw.txt" not in removed
    assert (tmp_path / "all_sources.npvt.raw.txt").exists()


def test_the_assembler_imports_cleanly_without_pythonpath(tmp_path):
    """The publish workflow runs this script with no PYTHONPATH.

    A lazy ``from huntx...`` import inside a function passed every pytest run -
    pytest puts src/ on sys.path - and then failed in production with
    ``ModuleNotFoundError: No module named 'huntx'``.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run(
        [sys.executable, "-c",
         "import runpy, sys; "
         "sys.argv=['assemble_generated_snapshot.py','--help']; "
         "runpy.run_path('scripts/assemble_generated_snapshot.py', run_name='__main__')"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert "ModuleNotFoundError" not in out.stderr, out.stderr
    assert "No module named 'huntx'" not in out.stderr, out.stderr


def test_the_assembler_resolves_canonical_names_through_the_shared_rule(tmp_path):
    """It must not re-derive the naming rule; the package owns it."""
    import os
    import subprocess
    import sys

    module = _load_assembler()
    assert module.output_filename("all_sources", "npvt.singbox.json") == "all_sources_singbox.json"

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run(
        [sys.executable, "-c",
         "import runpy, sys; "
         "sys.argv=['assemble_generated_snapshot.py','--help']; "
         "runpy.run_path('scripts/assemble_generated_snapshot.py', run_name='__main__')"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    # --help exits non-zero via argparse; the import must still have succeeded.
    assert "cannot import name 'output_filename'" not in out.stderr, out.stderr


def test_an_empty_directory_is_handled(tmp_path):
    module = _load_assembler()
    assert module.retire_legacy_derivatives(tmp_path) == set()


def test_the_retired_set_drives_the_manifest_and_catalog_prune(tmp_path):
    """retire_dashboard_derivatives drops the same names from both indexes."""
    module = _load_assembler()
    release = tmp_path / "docs" / "artifacts" / "release"
    release.mkdir(parents=True)
    _seed(release, LEGACY + CANONICAL)
    (release / "manifest.json").write_text(
        '{"schema_version": 1, "artifact_count": %d, "artifacts": [%s]}'
        % (
            len(LEGACY) + len(CANONICAL),
            ", ".join(
                '{"path": "%s"}' % name for name in sorted(LEGACY + CANONICAL)
            ),
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "catalog.json").write_text(
        '{"total_files": 1, "total_size": 7, "files": [{"path": "artifacts/release/all_sources.npvt.singbox.json", "size": 7}]}',
        encoding="utf-8",
    )

    module.retire_dashboard_derivatives(tmp_path / "docs")

    import json

    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in manifest["artifacts"]}
    assert "all_sources.npvt.singbox.json" not in paths
    assert "all_sources_singbox.json" in paths
    assert manifest["artifact_count"] == len(manifest["artifacts"])

    catalog = json.loads((tmp_path / "docs" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["files"] == []
    assert catalog["total_files"] == 0
    assert catalog["total_size"] == 0
