#!/usr/bin/env python3
"""Mirror verified generated outputs into the source branch without touching helpers."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path, PurePosixPath

ALLOWED_ROOTS = {"outputs", "outputs_dev"}
# The SPA dashboard data is pipeline-generated too, but the hand-maintained
# shell (index.html, assets/, sw.js, ...) must never become machine-managed.
MANAGED_DOCS_PATHS = {
    "docs/catalog.json",
    "docs/index.html",
    "docs/assets/js/data.js",
}
MANAGED_DOCS_PREFIXES = ("docs/artifacts/",)


def _is_managed_docs_path(value: str) -> bool:
    return value in MANAGED_DOCS_PATHS or value.startswith(MANAGED_DOCS_PREFIXES)


def parse_managed_path(raw: str) -> Path:
    value = raw.strip()
    if not value or value.startswith("#"):
        raise ValueError("managed path must be a non-comment value")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe managed path: {value}")
    if path.parts[0] == "docs":
        if not _is_managed_docs_path(value) or len(path.parts) < 2:
            raise ValueError(
                f"managed docs path must be catalog.json or below docs/artifacts/: {value}"
            )
        return Path(*path.parts)
    if len(path.parts) < 2 or path.parts[0] not in ALLOWED_ROOTS:
        raise ValueError(
            f"managed path must be below outputs/, outputs_dev/, or managed docs paths: {value}"
        )
    return Path(*path.parts)


def read_inventory(path: Path, *, required: bool) -> list[Path]:
    if not path.exists():
        if required:
            raise ValueError(f"required generated inventory is missing: {path}")
        return []

    managed: list[Path] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            item = parse_managed_path(value)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        key = item.as_posix()
        if key not in seen:
            seen.add(key)
            managed.append(item)
    if required and not managed:
        raise ValueError(f"required generated inventory is empty: {path}")
    return managed


def _ensure_within(root: Path, path: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its root: {path}") from exc


def _prune_empty_directories(repo_root: Path) -> None:
    for name in ALLOWED_ROOTS:
        root = repo_root / name
        if not root.is_dir():
            continue
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass


def prune_catalog_to_inventory(repo_root: Path, managed: list[Path]) -> bool:
    """Keep the catalog aligned with dashboard files included in the mirror."""
    catalog_path = repo_root / "docs" / "catalog.json"
    if not catalog_path.is_file():
        return False

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = catalog.get("files")
    if entries is None:
        return False
    if not isinstance(entries, list):
        raise ValueError(f"dashboard catalog is missing its files list: {catalog_path}")

    available = {path.as_posix()[len("docs/") :] for path in managed if path.as_posix().startswith("docs/artifacts/")}
    retained = [
        entry for entry in entries
        if not isinstance(entry, dict)
        or not isinstance(entry.get("path"), str)
        or not entry["path"].startswith("artifacts/")
        or entry["path"] in available
    ]

    changed = len(retained) != len(entries)
    if changed:
        catalog["files"] = retained
        catalog["total_files"] = len(retained)
        catalog["total_size"] = sum(
            int(entry.get("size") or 0)
            for entry in retained
            if isinstance(entry, dict)
        )
        size = float(catalog["total_size"])
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                catalog["total_size_str"] = (
                    f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
                )
                break
            size /= 1024
        catalog_path.write_text(
            json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    data_path = repo_root / "docs" / "assets" / "js" / "data.js"
    if data_path.is_file():
        data_content = data_path.read_text(encoding="utf-8")
        updated_data, replacements = re.subn(
            r"(?m)^export const FALLBACK_CATALOG = .*;$",
            "export const FALLBACK_CATALOG = "
            + json.dumps(catalog, separators=(",", ":"))
            + ";",
            data_content,
            count=1,
        )
        if replacements != 1:
            raise ValueError(f"dashboard data has no fallback catalog: {data_path}")
        if updated_data != data_content:
            data_path.write_text(updated_data, encoding="utf-8")
            changed = True
    return changed


def sync_generated_outputs(
    snapshot_root: Path,
    repo_root: Path,
    inventory_path: Path,
) -> tuple[int, int]:
    snapshot_root = snapshot_root.resolve()
    repo_root = repo_root.resolve()
    if not snapshot_root.is_dir():
        raise ValueError(f"snapshot root is missing: {snapshot_root}")
    if not repo_root.is_dir():
        raise ValueError(f"repository root is missing: {repo_root}")

    if not inventory_path.is_absolute():
        inventory_path = repo_root / inventory_path
    _ensure_within(repo_root, inventory_path, "inventory path")

    source_inventory = snapshot_root / "manifests" / "main-sync-files.txt"
    new_paths = read_inventory(source_inventory, required=True)
    old_paths = read_inventory(inventory_path, required=False)

    source_files: dict[Path, Path] = {}
    for relative in new_paths:
        source = snapshot_root / relative
        _ensure_within(snapshot_root, source, "snapshot file")
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"managed snapshot path is not a regular file: {source}")
        source_files[relative] = source

    new_set = set(new_paths)
    removed = 0
    for relative in old_paths:
        if relative in new_set:
            continue
        destination = repo_root / relative
        _ensure_within(repo_root, destination, "managed destination")
        if destination.is_symlink():
            raise ValueError(f"refusing to remove managed symlink: {destination}")
        if destination.exists():
            if not destination.is_file():
                raise ValueError(f"managed destination is not a file: {destination}")
            destination.unlink()
            removed += 1

    copied = 0
    for relative, source in source_files.items():
        destination = repo_root / relative
        _ensure_within(repo_root, destination, "managed destination")
        if destination.is_symlink():
            raise ValueError(f"refusing to overwrite managed symlink: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1

    prune_catalog_to_inventory(repo_root, new_paths)

    _prune_empty_directories(repo_root)
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_temp = inventory_path.with_name(inventory_path.name + ".tmp")
    inventory_temp.write_text(
        "\n".join(sorted(path.as_posix() for path in new_paths)) + "\n",
        encoding="utf-8",
    )
    inventory_temp.replace(inventory_path)
    return copied, removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--inventory-path",
        type=Path,
        default=Path(".github/huntx-generated-files.txt"),
    )
    parser.add_argument(
        "--prune-catalog-only",
        action="store_true",
        help="Remove catalog entries for artifact files absent from the managed inventory.",
    )
    args = parser.parse_args()

    if args.prune_catalog_only:
        root = args.repo_root.resolve()
        inventory = args.inventory_path
        if not inventory.is_absolute():
            inventory = root / inventory
        _ensure_within(root, inventory, "inventory path")
        managed = read_inventory(inventory, required=True)
        changed = prune_catalog_to_inventory(root, managed)
        print(f"Updated dashboard catalog: {'pruned unavailable files' if changed else 'already current'}.")
        return 0

    copied, removed = sync_generated_outputs(
        snapshot_root=args.snapshot_root,
        repo_root=args.repo_root,
        inventory_path=args.inventory_path,
    )
    print(f"Synchronized {copied} generated files; removed {removed} stale managed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
