import os
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

# Configuration
# Default to persist/data if not set, but respect env var.
# The orchestrator uses specific paths relative to DATA_DIR or CWD.
DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()

# Output directories
# 1. Latest outputs (user-friendly names) -> DATA_DIR/output
OUTPUT_DIR = Path(os.getenv("HUNTX_OUTPUT_DIR", DATA_DIR / "output")).resolve()
# 2. Dev outputs (cumulative) -> CWD/outputs_dev
#    Note: Orchestrator writes to CWD/outputs_dev. We assume generate_site_data is run from project root or can find it.
DEV_DIR = Path(os.getenv("HUNTX_DEV_DIR", "outputs_dev")).resolve()
# 3. Archive (historical) -> DATA_DIR/archive
ARCHIVE_DIR = Path(os.getenv("HUNTX_ARCHIVE_DIR", DATA_DIR / "archive")).resolve()

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

def get_file_metadata(filepath: Path, relative_path: str, tags: list = None) -> dict:
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
        "path": relative_path,
        "size": size_bytes,
        "size_str": size_str,
        "type": filepath.suffix.lstrip(".").upper() or "UNKNOWN",
        "ext": filepath.suffix.lstrip(".").upper() or "UNKNOWN",
        "tags": tags or [],
        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "hash": get_file_hash(filepath)
    }

def scan_directory(directory: Path, tag: str) -> list:
    """Scan a directory for files, copy them to artifacts/{tag}/, and return metadata."""
    files_meta = []
    if not directory.exists():
        print(f"Warning: Directory {directory} does not exist. Skipping.")
        return []

    print(f"Scanning {directory} (tag={tag})...")

    # Create subdirectory for this tag to avoid collisions
    target_subdir = ARTIFACTS_DIR / tag
    target_subdir.mkdir(parents=True, exist_ok=True)

    # rglob("*") includes subdirectories which we might want to skip or flatten.
    # We only want files.
    for item in sorted(directory.rglob("*")):
        if item.is_file():
            try:
                # Copy file
                dest = target_subdir / item.name
                shutil.copy2(item, dest)

                # Metadata
                # We pass the relative path including the subdirectory
                rel_path = f"artifacts/{tag}/{item.name}"
                meta = get_file_metadata(item, rel_path, tags=[tag])
                files_meta.append(meta)
                print(f"  Processed: {item.name} -> {rel_path}")
            except Exception as e:
                print(f"  Error processing {item.name}: {e}")
    return files_meta

def main():
    print(f"Generating site data...")
    print(f"  DATA_DIR: {DATA_DIR}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"  DEV_DIR: {DEV_DIR}")
    print(f"  ARCHIVE_DIR: {ARCHIVE_DIR}")

    all_files = []

    # Process output (latest)
    all_files.extend(scan_directory(OUTPUT_DIR, "latest"))

    # Process dev output (dev)
    all_files.extend(scan_directory(DEV_DIR, "dev"))

    # Process archive (archive)
    all_files.extend(scan_directory(ARCHIVE_DIR, "archive"))

    total_size = sum(f["size"] for f in all_files)

    catalog = {
        "generated_at": datetime.now().isoformat(),
        "total_files": len(all_files),
        "total_size": total_size,
        "total_size_str": f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB",
        "files": all_files
    }

    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"Catalog written to {CATALOG_FILE}")
    print(f"Artifacts copied to {ARTIFACTS_DIR}")
    print(f"Total files: {len(all_files)}")

if __name__ == "__main__":
    main()
