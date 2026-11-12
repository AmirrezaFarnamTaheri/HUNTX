"""Regression for the transitive minimatch GHSA-g3hv-75wg-m249."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _version(value):
    return tuple(int(chunk) for chunk in value.split(".")[:3])


def test_minimatch_is_patched_in_npm_lockfile():
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    instances = {
        path: metadata for path, metadata in lock["packages"].items()
        if path.endswith("node_modules/minimatch")
    }
    assert instances, "audit cannot prove safety without a locked minimatch version"
    for path, metadata in instances.items():
        assert _version(metadata["version"]) >= (11, 0, 1), path


def test_root_override_pins_patched_minimatch_through_eslint():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert _version(package["overrides"]["minimatch"]) >= (11, 0, 1)


def test_dependency_ci_rejects_moderate_severity_advisories():
    workflow = (ROOT / ".github" / "workflows" / "pr-validation.yml").read_text(encoding="utf-8")
    assert "npm audit --audit-level=moderate" in workflow
