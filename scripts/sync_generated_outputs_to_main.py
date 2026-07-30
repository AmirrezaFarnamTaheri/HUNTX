#!/usr/bin/env python3
"""Mirror verified generated outputs into the source branch without touching helpers."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path, PurePosixPath

ALLOWED_ROOTS = {"outputs", "outputs_dev"}


def parse_managed_path(raw: str) -> Path:
    value = raw.strip()
    if not value or value.startswith("#"):
        raise ValueError("managed path must be a non-comment value")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe managed path: {value}")
    if len(path.parts) < 2 or path.parts[0] not in ALLOWED_ROOTS:
        raise ValueError(f"managed path must be below outputs/ or outputs_dev/: {value}")
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
    args = parser.parse_args()

    copied, removed = sync_generated_outputs(
        snapshot_root=args.snapshot_root,
        repo_root=args.repo_root,
        inventory_path=args.inventory_path,
    )
    print(f"Synchronized {copied} generated files; removed {removed} stale managed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
