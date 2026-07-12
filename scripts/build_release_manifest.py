import json
import os
from pathlib import Path

from huntx.store.release_manifest import (
    build_release_manifest,
    verify_release_manifest,
    write_manifest_atomic,
)


def main() -> None:
    data_dir = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()
    dist_dir = data_dir / "dist"
    manifest_path = dist_dir / "manifest.json"
    files = [
        path
        for path in dist_dir.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    manifest = build_release_manifest(dist_dir, files)
    write_manifest_atomic(manifest_path, manifest)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_release_manifest(dist_dir, loaded)
    print(f"Validated {loaded['artifact_count']} release artifacts")


if __name__ == "__main__":
    main()