import hashlib
import json
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = REPO_ROOT / "outputs"
OUTPUTS_DEV_DIR = REPO_ROOT / "outputs_dev"
DOCS_DIR = REPO_ROOT / "docs"
ARTIFACTS_DIR = DOCS_DIR / "artifacts"
CATALOG_FILE = DOCS_DIR / "catalog.json"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_media_type(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".json") or ".json" in name:
        return "application/json"
    if name.endswith(".ovpn"):
        return "application/x-openvpn-profile"
    if name.endswith(".npvt"):
        return "application/x-npvt-subscription"
    if name.endswith(".b64sub") or name.endswith(".txt") or name.endswith(".md"):
        return "text/plain"
    if name.endswith(".opaque_bundle"):
        return "application/octet-stream"
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "application/octet-stream"


def _infer_tags_and_type(path: Path, section: str) -> tuple[str, list[str], str]:
    name = path.name.lower()
    tags = [section]
    ext = path.suffix.lstrip(".").upper() or "FILE"
    desc = ""

    if section == "release":
        tags.append("production")
        if "singbox" in name:
            ext = "SINGBOX"
            tags.extend(["singbox", "routing-profile", "outbounds"])
            desc = "Compiled Sing-box 1.10+ outbound routing profile with TLS/Reality rules"
        elif "v2ray" in name or "xray" in name:
            ext = "XRAY"
            tags.extend(["xray", "v2ray", "core-config"])
            desc = "Full Xray-core 1.8+ / V2Ray multi-protocol client configuration"
        elif "ovpn" in name:
            ext = "OVPN"
            tags.extend(["openvpn", "vpn", "gateway"])
            desc = "Standard OpenVPN multi-gateway client profile with TLS auth"
        elif "decoded.json" in name:
            ext = "JSON"
            tags.extend(["decoded", "parameters", "metadata"])
            desc = "Parsed and structured proxy connection parameters JSON dataset"
        elif "b64sub" in name:
            ext = "B64SUB"
            tags.extend(["subscription", "base64", "unified-feed"])
            desc = "Base64-encoded subscription feed for Shadowrocket, v2rayNG, and Streisand"
        elif "npvt" in name:
            ext = "NPVT"
            tags.extend(["subscription", "binary-feed"])
            desc = "Compact binary subscription feed for high-speed clients"
        elif "opaque_bundle" in name:
            ext = "BUNDLE"
            tags.extend(["bundle", "binary"])
            desc = "Cryptographically signed opaque proxy bundle"
        elif name.endswith(".md"):
            ext = "MD"
            tags.append("documentation")
            desc = "Production release documentation and checksum index"
    elif section == "dev":
        tags.append("cumulative")
        if name.startswith("proxies_chunk_"):
            ext = "CHUNK"
            tags.extend(["chunk", "split-feed", "lightweight"])
            desc = f"Lightweight split feed chunk ({path.name}) for bandwidth-constrained clients"
        elif "b64sub" in name:
            ext = "B64SUB"
            tags.extend(["subscription", "base64", "all-time"])
            desc = "All-time cumulative Base64 subscription feed across 49+ sources"
        elif name == "proxies.json":
            ext = "JSON"
            tags.extend(["aggregated", "all-time", "full-json"])
            desc = "Complete all-time cumulative proxy dataset with first-seen timestamps"
        elif name == "proxies.txt":
            ext = "TXT"
            tags.extend(["raw-uris", "deduped", "all-time"])
            desc = "All-time cumulative raw proxy URI list (SHA-256 deduplicated)"
        elif name == "_manifest.json":
            ext = "MANIFEST"
            tags.extend(["manifest", "telemetry", "state"])
            desc = "Durable cumulative first-seen timestamp manifest index"
        elif name.endswith(".md"):
            ext = "MD"
            tags.append("documentation")
            desc = "Development and cumulative output documentation"

    return ext, tags, desc


def generate_catalog_and_sync_artifacts() -> dict:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    catalog_entries: list[dict] = []
    seen_destinations: set[str] = set()

    sources = [
        ("release", OUTPUTS_DIR),
        ("dev", OUTPUTS_DEV_DIR),
    ]

    for section, source_dir in sources:
        if not source_dir.exists():
            continue
        dest_dir = ARTIFACTS_DIR / section
        dest_dir.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(source_dir.rglob("*")):
            if not src_file.is_file():
                continue

            rel_to_source = src_file.relative_to(source_dir)
            dst_file = dest_dir / rel_to_source
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_file, dst_file)

            destination_rel_docs = dst_file.relative_to(DOCS_DIR).as_posix()
            if destination_rel_docs in seen_destinations:
                continue
            seen_destinations.add(destination_rel_docs)

            file_size = src_file.stat().st_size
            digest = _sha256(src_file)
            ext, tags, desc = _infer_tags_and_type(src_file, section)

            entry = {
                "filename": src_file.name,
                "path": destination_rel_docs,
                "section": section,
                "size": file_size,
                "size_str": _format_size(file_size),
                "type": ext,
                "ext": ext,
                "tags": tags,
                "description": desc,
                "sha256": digest,
                "hash": digest[:8],
                "media_type": _infer_media_type(src_file),
                "last_modified": datetime.fromtimestamp(
                    src_file.stat().st_mtime, timezone.utc
                ).isoformat(),
            }
            catalog_entries.append(entry)

    total_size = sum(e["size"] for e in catalog_entries)
    catalog = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(catalog_entries),
        "total_size": total_size,
        "total_size_str": _format_size(total_size),
        "files": catalog_entries,
    }

    CATALOG_FILE.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "schema_version": 1,
        "artifact_count": len(catalog_entries),
        "artifacts": [
            {
                "path": e["path"].replace("artifacts/", "", 1),
                "size": e["size"],
                "sha256": e["sha256"],
                "media_type": e["media_type"],
            }
            for e in catalog_entries
        ],
    }
    (ARTIFACTS_DIR / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return catalog


def main() -> None:
    catalog = generate_catalog_and_sync_artifacts()
    print(f"Catalog written to {CATALOG_FILE} with {catalog['total_files']} files ({catalog['total_size_str']})")


if __name__ == "__main__":
    main()
