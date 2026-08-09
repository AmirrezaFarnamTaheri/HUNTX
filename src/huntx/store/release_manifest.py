from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    size: int
    sha256: str
    media_type: str


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {"schema_version", "artifact_count", "artifacts"}
_ARTIFACT_KEYS = {"path", "size", "sha256", "media_type"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    if path.name.endswith(".decoded.json") or path.suffix == ".json":
        return "application/json"
    if path.suffix in {".yaml", ".yml"}:
        return "application/yaml"
    if path.suffix == ".zip":
        return "application/zip"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _validate_artifact(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"Artifact is not a regular file: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Empty artifact is not publishable: {path}")
    if path.is_symlink():
        raise ValueError(f"Symlink artifacts are forbidden: {path}")
    if path.suffix == ".json" or path.name.endswith(".decoded.json"):
        json.loads(path.read_text(encoding="utf-8"))


def _inspect_artifact(path: Path) -> tuple[int, str]:
    """Hash and size one already-validated file through a single handle."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    digest = hashlib.sha256()
    byte_count = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Artifact is not a regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                byte_count += len(chunk)
        after = os.fstat(fd)
        identity_before = (before.st_dev, before.st_ino, before.st_size)
        identity_after = (after.st_dev, after.st_ino, after.st_size)
        if identity_before != identity_after or byte_count != after.st_size:
            raise ValueError(f"Artifact changed while being inspected: {path}")
        return byte_count, digest.hexdigest()
    finally:
        os.close(fd)


def build_release_manifest(root: Path, files: Iterable[Path]) -> dict:
    root = root.resolve()
    records: list[ArtifactRecord] = []
    seen_paths: set[str] = set()
    for candidate in sorted(files, key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"Symlink artifacts are forbidden: {candidate}")
        path = candidate.resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Artifact escapes release root: {candidate}") from exc
        if relative in seen_paths:
            raise ValueError(f"Duplicate artifact coordinate: {relative}")
        seen_paths.add(relative)
        _validate_artifact(path)
        size, digest = _inspect_artifact(path)
        records.append(
            ArtifactRecord(
                path=relative,
                size=size,
                sha256=digest,
                media_type=_media_type(path),
            )
        )
    if not records:
        raise ValueError("A release must contain at least one validated artifact")
    return {
        "schema_version": 1,
        "artifact_count": len(records),
        "artifacts": [asdict(record) for record in records],
    }


def write_manifest_atomic(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def verify_release_manifest(root: Path, manifest: dict) -> None:
    root = root.resolve()
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise ValueError("Manifest has unexpected or missing fields")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest schema version")
    artifacts = manifest.get("artifacts")
    artifact_count = manifest.get("artifact_count")
    if (
        not isinstance(artifact_count, int)
        or isinstance(artifact_count, bool)
        or artifact_count <= 0
        or not isinstance(artifacts, list)
        or artifact_count != len(artifacts)
    ):
        raise ValueError("Manifest artifact count is inconsistent")
    seen_paths: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict) or set(record) != _ARTIFACT_KEYS:
            raise ValueError("Artifact record has unexpected or missing fields")
        relative = record.get("path")
        if not isinstance(relative, str) or "\\" in relative:
            raise ValueError("Manifest path must be a string")
        pure = PurePosixPath(relative)
        if (
            not relative
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
            or pure.as_posix() != relative
            or relative in seen_paths
        ):
            raise ValueError(f"Manifest path is not canonical: {relative}")
        seen_paths.add(relative)
        candidate = root.joinpath(*pure.parts)
        if candidate.is_symlink():
            raise ValueError(f"Symlink artifacts are forbidden: {candidate}")
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Manifest path escapes release root: {relative}") from exc
        _validate_artifact(path)
        expected_size = record.get("size")
        expected_digest = record.get("sha256")
        media_type = record.get("media_type")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size <= 0:
            raise ValueError(f"Invalid artifact size: {relative}")
        if not isinstance(expected_digest, str) or not _DIGEST_RE.fullmatch(expected_digest):
            raise ValueError(f"Invalid artifact digest: {relative}")
        if not isinstance(media_type, str) or not media_type:
            raise ValueError(f"Invalid artifact media type: {relative}")
        size, digest = _inspect_artifact(path)
        if size != expected_size:
            raise ValueError(f"Artifact size mismatch: {relative}")
        if digest != expected_digest:
            raise ValueError(f"Artifact digest mismatch: {relative}")
