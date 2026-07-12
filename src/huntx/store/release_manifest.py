from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    size: int
    sha256: str
    media_type: str


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


def build_release_manifest(root: Path, files: Iterable[Path]) -> dict:
    root = root.resolve()
    records: list[ArtifactRecord] = []
    seen_paths: set[str] = set()
    for candidate in sorted(files, key=lambda item: item.as_posix()):
        path = candidate.resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Artifact escapes release root: {candidate}") from exc
        if relative in seen_paths:
            raise ValueError(f"Duplicate artifact coordinate: {relative}")
        seen_paths.add(relative)
        _validate_artifact(path)
        records.append(
            ArtifactRecord(
                path=relative,
                size=path.stat().st_size,
                sha256=_sha256(path),
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
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def verify_release_manifest(root: Path, manifest: dict) -> None:
    root = root.resolve()
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or manifest.get("artifact_count") != len(artifacts):
        raise ValueError("Manifest artifact count is inconsistent")
    for record in artifacts:
        relative = record.get("path")
        if not isinstance(relative, str):
            raise ValueError("Manifest path must be a string")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Manifest path escapes release root: {relative}") from exc
        _validate_artifact(path)
        if path.stat().st_size != record.get("size"):
            raise ValueError(f"Artifact size mismatch: {relative}")
        if _sha256(path) != record.get("sha256"):
            raise ValueError(f"Artifact digest mismatch: {relative}")