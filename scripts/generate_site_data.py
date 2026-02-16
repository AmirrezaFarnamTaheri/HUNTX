import os
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

# Configuration
DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()
DIST_DIR = DATA_DIR / "dist"
DOCS_DIR = Path("docs").resolve()
ARTIFACTS_DIR = DOCS_DIR / "artifacts"
CATALOG_FILE = DOCS_DIR / "catalog.json"

# Ensure directories exist
DOCS_DIR.mkdir(parents=True, exist_ok=True)
if ARTIFACTS_DIR.exists():
    shutil.rmtree(ARTIFACTS_DIR)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

def get_file_hash(filepath: Path) -> str:
    """Calculate MD5 hash of a file efficiently."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()[:8]

def get_file_metadata(filepath: Path) -> dict:
    stat = filepath.stat()
    size_bytes = stat.st_size

    # Human readable size
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

    return {
        "filename": filepath.name,
        "path": f"artifacts/{filepath.name}",
        "size": size_bytes,
        "size_str": size_str,
        "type": filepath.suffix.lstrip(".").upper() or "UNKNOWN",
        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "hash": get_file_hash(filepath)
    }

def main():
    print(f"Generating site data from {DIST_DIR}...")

    files = []
    total_size = 0

    if not DIST_DIR.exists():
        print(f"Warning: {DIST_DIR} does not exist. Using empty catalog.")
    else:
        for item in sorted(DIST_DIR.rglob("*")):
            if item.is_file():
                try:
                    # Copy file
                    dest = ARTIFACTS_DIR / item.name
                    shutil.copy2(item, dest)

                    # Metadata
                    meta = get_file_metadata(item)
                    files.append(meta)
                    total_size += meta["size"]
                    print(f"  Processed: {item.name}")
                except Exception as e:
                    print(f"  Error processing {item.name}: {e}")

    catalog = {
        "generated_at": datetime.now().isoformat(),
        "total_files": len(files),
        "total_size": total_size,
        "total_size_str": f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB",
        "files": files
    }

    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"Catalog written to {CATALOG_FILE}")
    print(f"Artifacts copied to {ARTIFACTS_DIR}")

if __name__ == "__main__":
    main()
