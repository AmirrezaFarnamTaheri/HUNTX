import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from huntx.store.release_manifest import (
    build_release_manifest,
    verify_release_manifest,
    write_manifest_atomic,
)

DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()
DIST_DIR = DATA_DIR / "dist"
DOCS_DIR = Path("docs").resolve()
ARTIFACTS_DIR = DOCS_DIR / "artifacts"
CATALOG_FILE = DOCS_DIR / "catalog.json"


def _load_verified_manifest() -> dict:
    manifest_path = DIST_DIR / "manifest.json"
    files = [path for path in DIST_DIR.rglob("*") if path.is_file() and path != manifest_path]
    manifest = build_release_manifest(DIST_DIR, files)
    write_manifest_atomic(manifest_path, manifest)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_release_manifest(DIST_DIR, loaded)
    return loaded


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _copy_verified_artifacts(manifest: dict) -> list[dict]:
    if ARTIFACTS_DIR.exists():
        shutil.rmtree(ARTIFACTS_DIR)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    catalog_entries: list[dict] = []
    seen_destinations: set[str] = set()
    for record in manifest["artifacts"]:
        relative = Path(record["path"])
        source = (DIST_DIR / relative).resolve()
        source.relative_to(DIST_DIR)
        destination = ARTIFACTS_DIR / relative
        destination_key = destination.relative_to(DOCS_DIR).as_posix()
        if destination_key in seen_destinations:
            raise RuntimeError(f"Duplicate site artifact coordinate: {destination_key}")
        seen_destinations.add(destination_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        catalog_entries.append(
            {
                "filename": relative.name,
                "path": destination_key,
                "size": record["size"],
                "size_str": _format_size(record["size"]),
                "media_type": record["media_type"],
                "sha256": record["sha256"],
                "tags": ["release"],
            }
        )
    return catalog_entries


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_verified_manifest()
    files = _copy_verified_artifacts(manifest)
    total_size = sum(item["size"] for item in files)
    catalog = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_manifest": "artifacts/manifest.json",
        "total_files": len(files),
        "total_size": total_size,
        "total_size_str": _format_size(total_size),
        "files": files,
    }
    CATALOG_FILE.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(DIST_DIR / "manifest.json", ARTIFACTS_DIR / "manifest.json")
    print(f"Catalog written to {CATALOG_FILE} with {len(files)} verified artifacts")


if __name__ == "__main__":
    main()
