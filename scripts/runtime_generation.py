"""Build and verify immutable runtime-state generations.

The S3 workflow uploads a complete generation first and replaces the small
``current.json`` pointer only after every file and the manifest are durable.
This module deliberately contains no network code so the integrity protocol
is deterministic and unit-testable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

_GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_generation(generation: Any) -> str:
    value = str(generation)
    if not _GENERATION_RE.fullmatch(value):
        raise RuntimeError(f"invalid generation identifier: {value!r}")
    return value


def _safe_relative_path(value: Any) -> PurePosixPath:
    raw = str(value)
    path = PurePosixPath(raw)
    if not raw or "\\" in raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe manifest path: {raw!r}")
    return path


def build_manifest(root: Path, generation: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    generation = _validate_generation(generation)
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"generation contains symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        files[relative] = {
            "sha256": _digest_file(path),
            "size": path.stat().st_size,
        }
    if "state.db" not in files:
        raise RuntimeError("generation is missing state.db")
    return {
        "schema_version": 1,
        "generation": generation,
        "files": files,
    }


def verify_manifest(root: Path, manifest: dict[str, Any]) -> None:
    root = root.resolve(strict=True)
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported runtime manifest schema")
    _validate_generation(manifest.get("generation"))
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        raise RuntimeError("runtime manifest files must be an object")

    expected: set[str] = set()
    for raw_relative, metadata in declared.items():
        relative = _safe_relative_path(raw_relative)
        relative_text = relative.as_posix()
        expected.add(relative_text)
        if not isinstance(metadata, dict):
            raise RuntimeError(f"invalid metadata for {relative_text}")
        digest = metadata.get("sha256")
        size = metadata.get("size")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise RuntimeError(f"invalid digest for {relative_text}")
        if not isinstance(size, int) or size < 0:
            raise RuntimeError(f"invalid size for {relative_text}")
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"generation file missing: {relative_text}")
        if path.stat().st_size != size:
            raise RuntimeError(f"size mismatch for {relative_text}")
        if _digest_file(path) != digest:
            raise RuntimeError(f"digest mismatch for {relative_text}")

    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and not path.is_symlink()}
    if actual != expected:
        raise RuntimeError(
            "generation file set mismatch: "
            f"missing={sorted(expected - actual)} "
            f"unexpected={sorted(actual - expected)}"
        )


def build_pointer(
    generation: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    generation = _validate_generation(generation)
    if manifest.get("generation") != generation:
        raise RuntimeError("pointer generation does not match manifest")
    return {
        "schema_version": 1,
        "generation": generation,
        "manifest_sha256": hashlib.sha256(_canonical_bytes(manifest)).hexdigest(),
    }


def validate_pointer(
    pointer: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> str:
    if pointer.get("schema_version") != 1:
        raise RuntimeError("unsupported runtime pointer schema")
    generation = _validate_generation(pointer.get("generation"))
    digest = pointer.get("manifest_sha256")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise RuntimeError("invalid runtime pointer manifest digest")
    if manifest is not None:
        if manifest.get("generation") != generation:
            raise RuntimeError("pointer and manifest generations differ")
        actual = hashlib.sha256(_canonical_bytes(manifest)).hexdigest()
        if actual != digest:
            raise RuntimeError("runtime manifest does not match pointer")
    return generation


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--generation", required=True)
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--pointer", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)

    pointer = commands.add_parser("validate-pointer")
    pointer.add_argument("--pointer", type=Path, required=True)
    pointer.add_argument("--manifest", type=Path)

    args = parser.parse_args()
    if args.command == "build":
        manifest = build_manifest(args.root, args.generation)
        current = build_pointer(args.generation, manifest)
        args.manifest.write_bytes(_canonical_bytes(manifest))
        args.pointer.write_bytes(_canonical_bytes(current))
    elif args.command == "verify":
        verify_manifest(args.root, _read_json(args.manifest))
    else:
        pointer_manifest = _read_json(args.manifest) if args.manifest is not None else None
        print(
            validate_pointer(
                _read_json(args.pointer),
                pointer_manifest,
            )
        )


if __name__ == "__main__":
    main()
