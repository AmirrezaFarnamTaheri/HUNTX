#!/usr/bin/env python3
"""Assemble a verified, deterministic generated-output publication snapshot."""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import gzip
import hashlib
import json
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

# The publish workflow runs this script directly, without PYTHONPATH=src, so the
# package it shares naming rules with has to be importable from the repo this
# file lives in. Retiring legacy derivatives must resolve a canonical filename
# through huntx.core.output_ownership rather than re-deriving the rule here.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from huntx.core.output_ownership import output_filename  # noqa: E402
from huntx.formats.npvt import (  # noqa: E402
    strip_proxy_remark, canonical_proxy_identity, add_clean_remark,
)

ManifestValue = float | int | str
LEGACY_FIRST_SEEN = 0
_MANIFEST_CHUNK_BYTES = 16 * 1024 * 1024
# Preserve historical Sing-box/Xray full-profile URLs and frozen URI aliases.
# Obsolete dotted decoded datasets and NekoBox artifacts are retired only once
# their canonical replacements exist, preventing old telemetry from resurfacing.
_DERIVED_SUFFIXES = ("decoded.json", "nekobox.json")


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def retire_legacy_derivatives(directory: Path) -> set[str]:
    """Remove dotted derivatives only when their canonical replacement exists.

    The canonical name is taken from ``output_filename`` rather than rebuilt
    here. Re-deriving the naming rule in a second place meant this kept looking
    for the pre-rename ``{route}_{fmt}_{suffix}`` spelling, so after the rename
    it found the legacy file, decided no replacement existed, and left both in
    the snapshot forever.
    """
    removed: set[str] = set()
    for fmt in ("npvt", "npvtsub"):
        for suffix in _DERIVED_SUFFIXES:
            ending = f".{fmt}.{suffix}"
            for legacy in directory.glob(f"*{ending}"):
                route = legacy.name.removesuffix(ending)
                if not route or not legacy.is_file():
                    continue
                canonical = directory / output_filename(route, f"{fmt}.{suffix}")
                # A retired format whose canonical name is the legacy name itself
                # must not delete the only copy of itself.
                if canonical.is_file() and canonical.resolve() != legacy.resolve():
                    legacy.unlink()
                    removed.add(legacy.name)
    return removed


def retire_dashboard_derivatives(docs_dir: Path) -> None:
    release_dir = docs_dir / "artifacts" / "release"
    removed = retire_legacy_derivatives(release_dir)
    if not removed:
        return

    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("release manifest is missing its artifacts list")
    manifest["artifacts"] = [item for item in artifacts if item.get("path") not in removed]
    manifest["artifact_count"] = len(manifest["artifacts"])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    catalog_path = docs_dir / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    files = catalog.get("files")
    if isinstance(files, list):
        retired_paths = {f"artifacts/release/{name}" for name in removed}
        retained = [item for item in files if item.get("path") not in retired_paths]
        if len(retained) != len(files):
            catalog["files"] = retained
            catalog["total_files"] = len(retained)
            catalog["total_size"] = sum(item["size"] for item in retained)
            catalog["total_size_str"] = _format_size(catalog["total_size"])
            catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


def first_dir(root: Path, name: str) -> Path | None:
    for path in [root / name, *root.rglob(name)]:
        if path.is_dir():
            return path
    return None


def _b64_decode_safe(data: str) -> str:
    normalized = data.replace("-", "+").replace("_", "/")
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    decoded = base64.b64decode(normalized, validate=True)
    return decoded.decode("utf-8")


def _normalise_manifest_value(value: Any) -> ManifestValue:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return value
    raise ValueError("dev manifest timestamps must be scalar values")


def _earlier(candidate: ManifestValue, existing: ManifestValue) -> bool:
    try:
        return float(candidate) < float(existing)
    except (TypeError, ValueError):
        return str(candidate) < str(existing)


def normalise_manifest(raw: Any, source: Path) -> dict[str, ManifestValue]:
    if not isinstance(raw, dict):
        raise ValueError(f"dev manifest root must be an object: {source}")

    normalised: dict[str, ManifestValue] = {}
    for raw_uri, raw_first_seen in raw.items():
        if not isinstance(raw_uri, str):
            raise ValueError(f"dev manifest URI keys must be strings: {source}")
        uri = strip_proxy_remark(raw_uri.strip())
        if not uri or "://" not in uri:
            raise ValueError(f"invalid proxy identity in dev manifest: {source}")
        first_seen = _normalise_manifest_value(raw_first_seen)
        previous = normalised.get(uri)
        if previous is None or _earlier(first_seen, previous):
            normalised[uri] = first_seen
    return normalised


def load_dev_manifest(path: Path | None) -> dict[str, ManifestValue]:
    if path is None:
        return {}
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            index_path = path.with_name(path.name + ".gz.index.json")
            if not index_path.exists():
                return {}
            index = json.loads(index_path.read_text(encoding="utf-8"))
            parts = index.get("parts") if isinstance(index, dict) else None
            if not isinstance(parts, list) or not parts or not all(
                isinstance(part, str) and Path(part).name == part for part in parts
            ):
                raise ValueError("compressed dev manifest index has invalid parts")
            compressed = b"".join((index_path.parent / part).read_bytes() for part in parts)
            raw = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, gzip.BadGzipFile) as exc:
        raise ValueError(f"could not read dev manifest {path}: {exc}") from exc
    return normalise_manifest(raw, path)


def write_compressed_dev_manifest(dev_dir: Path, manifest: dict[str, ManifestValue]) -> None:
    """Write deterministic small gzip members so every Git blob stays below 100 MB."""
    for stale_part in dev_dir.glob("_manifest.json.gz.part*"):
        stale_part.unlink()
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    parts: list[str] = []
    for offset in range(0, len(payload), _MANIFEST_CHUNK_BYTES):
        name = f"_manifest.json.gz.part{len(parts) + 1:04d}"
        (dev_dir / name).write_bytes(
            gzip.compress(payload[offset : offset + _MANIFEST_CHUNK_BYTES], compresslevel=9, mtime=0)
        )
        parts.append(name)
    if not parts:
        name = "_manifest.json.gz.part0001"
        (dev_dir / name).write_bytes(gzip.compress(b"{}", compresslevel=9, mtime=0))
        parts.append(name)
    index = {"encoding": "concatenated-gzip-json", "parts": parts}
    (dev_dir / "_manifest.json.gz.index.json").write_text(
        json.dumps(index, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def compact_semantic_manifest(manifest: dict[str, ManifestValue]) -> dict[str, ManifestValue]:
    """Merge equivalent URI spellings without discarding distinct credentials.

    Retain the earliest known timestamp and one valid original URI; the key
    itself is a normalized *identity* and is never exported as a rewritten URI.
    Repeated keys preserve their original order, TLS/password/path differences
    remain independent, and a stable lexical tie-break makes publish idempotent.
    """
    selected: dict[str, tuple[str, ManifestValue]] = {}
    for uri, first_seen in sorted(manifest.items()):
        fingerprint = canonical_proxy_identity(uri)
        prior = selected.get(fingerprint)
        if prior is None:
            selected[fingerprint] = (uri, first_seen)
        elif str(prior[1]) in {"0", "0.0"} and str(first_seen) not in {"0", "0.0"}:
            # The historic 0 is "first seen unknown", NOT epoch zero.
            # A known source timestamp always outranks that sentinel.
            selected[fingerprint] = (prior[0], first_seen)
        elif str(first_seen) not in {"0", "0.0"} and _earlier(first_seen, prior[1]):
            selected[fingerprint] = (prior[0], first_seen)
    return {uri: first_seen for uri, first_seen in selected.values()}


def merge_dev_manifests(
    previous: dict[str, ManifestValue],
    current: dict[str, ManifestValue],
) -> dict[str, ManifestValue]:
    merged = dict(previous)
    for uri, first_seen in current.items():
        existing = merged.get(uri)
        if existing is None or _earlier(first_seen, existing):
            merged[uri] = first_seen
    return compact_semantic_manifest(merged)


def seed_missing_identities(
    manifest: dict[str, ManifestValue],
    identity_seed: dict[str, ManifestValue],
) -> dict[str, ManifestValue]:
    seeded = dict(manifest)
    for uri, first_seen in identity_seed.items():
        seeded.setdefault(uri, first_seen)
    return compact_semantic_manifest(seeded)


def _add_legacy_identity(
    manifest: dict[str, ManifestValue],
    candidate: Any,
    first_seen: Any = LEGACY_FIRST_SEEN,
) -> None:
    if not isinstance(candidate, str):
        return
    value = candidate.strip()
    if not value or value.startswith("#") or "://" not in value:
        return
    uri = strip_proxy_remark(value)
    if not uri or "://" not in uri:
        return
    try:
        timestamp = _normalise_manifest_value(first_seen)
    except ValueError:
        timestamp = LEGACY_FIRST_SEEN
    manifest.setdefault(uri, timestamp)


def _load_legacy_json(path: Path, manifest: dict[str, ManifestValue]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        proxies = raw.get("proxies", [])
    elif isinstance(raw, list):
        proxies = raw
    else:
        raise ValueError(f"legacy proxy JSON root must be an object or array: {path}")

    if not isinstance(proxies, list):
        raise ValueError(f"legacy proxy JSON proxies must be an array: {path}")
    for item in proxies:
        if isinstance(item, str):
            _add_legacy_identity(manifest, item)
        elif isinstance(item, dict):
            _add_legacy_identity(
                manifest,
                item.get("uri") or item.get("line"),
                item.get("first_seen", LEGACY_FIRST_SEEN),
            )


def load_legacy_dev_identities(dev_dir: Path | None) -> dict[str, ManifestValue]:
    """Recover cumulative identities from pre-manifest output layouts.

    Historical repositories may have a blank or missing ``_manifest.json`` while
    still containing a very large rendered proxy list. Those identities are data,
    not disposable presentation residue. Known timestamps from a manifest or JSON
    record are loaded before text-only identities; identities recovered only from
    rendered files receive the sentinel timestamp ``0``.
    """
    if dev_dir is None or not dev_dir.is_dir():
        return {}

    manifest: dict[str, ManifestValue] = {}
    errors: list[str] = []
    nonempty_sources: list[Path] = []

    manifest_path = dev_dir / "_manifest.json"
    compressed_index = manifest_path.with_name(manifest_path.name + ".gz.index.json")
    if (manifest_path.is_file() and manifest_path.stat().st_size > 0) or compressed_index.is_file():
        nonempty_sources.append(manifest_path)
        try:
            manifest.update(load_dev_manifest(manifest_path))
        except ValueError as exc:
            errors.append(str(exc))

    json_path = dev_dir / "proxies.json"
    if json_path.is_file() and json_path.stat().st_size > 0:
        nonempty_sources.append(json_path)
        try:
            _load_legacy_json(json_path, manifest)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"could not read legacy proxy JSON {json_path}: {exc}")

    text_path = dev_dir / "proxies.txt"
    if text_path.is_file() and text_path.stat().st_size > 0:
        nonempty_sources.append(text_path)
        try:
            with text_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    _add_legacy_identity(manifest, line)
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"could not read legacy proxy list {text_path}: {exc}")

    b64_path = dev_dir / "proxies_b64sub.txt"
    if not manifest and b64_path.is_file() and b64_path.stat().st_size > 0:
        nonempty_sources.append(b64_path)
        try:
            decoded = _b64_decode_safe(b64_path.read_text(encoding="utf-8").strip())
            for line in decoded.splitlines():
                _add_legacy_identity(manifest, line)
        except (OSError, UnicodeDecodeError, ValueError, binascii.Error) as exc:
            errors.append(f"could not read legacy base64 subscription {b64_path}: {exc}")

    if nonempty_sources and not manifest:
        details = "; ".join(errors) if errors else "no proxy identities were found"
        source_list = ", ".join(str(path) for path in nonempty_sources)
        raise ValueError(f"legacy cumulative output could not be recovered from {source_list}: {details}")
    return manifest


def _timestamp_sort_key(value: ManifestValue) -> tuple[int, float | str]:
    try:
        return (1, float(value))
    except (TypeError, ValueError):
        return (0, str(value))


def _display_timestamp(source_created_at: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(source_created_at.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return source_created_at


def write_dev_outputs(
    dev_dir: Path,
    manifest: dict[str, ManifestValue],
    source_created_at: str,
) -> None:
    dev_dir.mkdir(parents=True, exist_ok=True)
    manifest = compact_semantic_manifest(manifest)
    manifest_path = dev_dir / "_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_compressed_dev_manifest(dev_dir, manifest)

    sorted_uris = sorted(manifest)
    sorted_uris.sort(key=lambda uri: _timestamp_sort_key(manifest[uri]), reverse=True)
    remark_counter: dict[str, int] = {}
    remarked_uris = [add_clean_remark(uri, remark_counter) for uri in sorted_uris]
    timestamp = _display_timestamp(source_created_at)
    # An empty timestamp must not leave a dangling separator behind:
    # trailing whitespace would trip `git diff --check` on the snapshot.
    title = (
        f"# huntx proxy list — {timestamp}"
        if timestamp
        else "# huntx proxy list"
    )

    header = (
        f"{title}\n"
        f"# All-time cumulative history — {len(remarked_uris)} unique URIs\n"
        "# One proxy URI per line\n\n"
    )
    (dev_dir / "proxies.txt").write_text(
        header + "\n".join(remarked_uris) + "\n",
        encoding="utf-8",
    )

    plain = "\n".join(remarked_uris)
    encoded = base64.b64encode(plain.encode("utf-8")).decode("ascii")
    (dev_dir / "proxies_b64sub.txt").write_text(encoded + "\n", encoding="utf-8")

    wrapped = {
        "_generated": timestamp,
        "_scope": "all_time_cumulative",
        "_count": len(sorted_uris),
        "proxies": [
            {"uri": remarked, "first_seen": manifest[raw]}
            for raw, remarked in zip(sorted_uris, remarked_uris)
        ],
    }
    (dev_dir / "proxies.json").write_text(
        json.dumps(wrapped, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def require_nonempty_tree(path: Path | None, label: str) -> Path:
    if path is None or not path.is_dir():
        raise ValueError(f"missing required {label} directory")
    if not any(item.is_file() and item.stat().st_size > 0 for item in path.rglob("*")):
        raise ValueError(f"required {label} directory has no non-empty files")
    return path


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def _refresh_frontend_index(project_root: Path) -> None:
    """Render the dashboard shell from the final staged catalog and data."""
    script = Path(__file__).with_name("update_frontend.py")
    namespace = runpy.run_path(str(script))
    writer = namespace.get("write_index")
    if not callable(writer):
        raise RuntimeError(f"frontend generator does not expose write_index: {script}")
    writer(project_root)


def _catalog_dev_trio(docs_dir: Path, dev_dir: Path) -> None:
    """Expose only the canonical cumulative dataset in the staged catalog.

    The raw TXT and Base64 cumulative feeds remain deployed for direct/backward-
    compatible URLs, but they are implementation variants rather than distinct
    final products and therefore stay out of the public artifact browser.
    """
    catalog_path = docs_dir / "catalog.json"
    if not catalog_path.is_file():
        return
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    files_list = catalog.get("files") or []
    known = {entry.get("filename") for entry in files_list}
    total_size = int(catalog.get("total_size") or 0)
    added = False
    for name in ("proxies.json",):
        source = dev_dir / name
        if not source.is_file() or name in known:
            continue
        payload = source.read_bytes()
        total_size += len(payload)
        files_list.append({
            "filename": name,
            "path": f"artifacts/dev/{name}",
            "size": len(payload),
            "size_str": _format_size(len(payload)),
            "media_type": "application/json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "tags": ["dev", "cumulative", "dataset"],
            "section": "dev",
            "type": "JSON",
            "ext": "JSON",
            "description": "All-time cumulative proxy dataset (outside the release manifest)",
        })
        added = True
    if not added:
        return
    catalog["files"] = files_list
    catalog["total_files"] = len(files_list)
    catalog["total_size"] = total_size
    catalog["total_size_str"] = _format_size(total_size)
    catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _proxy_hashes(directory: Path | None, filename: str) -> set[str] | None:
    """Return normalized connection digests, or None if feed was unavailable."""
    if directory is None or not (directory / filename).is_file():
        return None
    found: set[str] = set()
    for line in (directory / filename).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        identity = canonical_proxy_identity(line.strip())
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if digest in found:
            raise ValueError("Released proxy feed contains duplicate semantic identities")
        found.add(digest)
    return found


def build_proxy_churn_report(
    current_outputs: Path, previous_outputs: Path | None
) -> dict[str, Any]:
    """Compare connection identities; a disappearance is not permanent death."""
    current = _proxy_hashes(current_outputs, "all_sources.txt")
    previous = _proxy_hashes(previous_outputs, "all_sources.txt")
    alternate = _proxy_hashes(current_outputs, "all_sources_sub.txt")
    if current is None:
        return {"schema_version": 1, "status": "current_primary_missing"}
    decisions: dict[str, str] = {}
    gate_path = current_outputs / "all_sources_gate.json"
    if gate_path.is_file():
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if gate.get("schema_version") == 1 and isinstance(gate.get("identities"), dict):
            decisions = {
                key: value for key, value in gate["identities"].items()
                if isinstance(key, str) and isinstance(value, str)
            }
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "complete" if previous is not None else "previous_unavailable",
        "identity": "sha256-of-canonical-proxy-identity",
        "current_count": len(current),
        "previous_count": len(previous) if previous is not None else None,
        "retained_count": len(current & previous) if previous is not None else None,
        "appeared_count": len(current - previous) if previous is not None else None,
        "disappeared_count": len(previous - current) if previous is not None else None,
        "appeared": sorted(current - previous) if previous is not None else [],
        "disappeared": {
            key: {
                "status": "absent_from_current_published_snapshot",
                "current_gate_status": decisions.get(key, "not_in_current_gate_candidates"),
                "permanently_dead": False,
            }
            for key in sorted(previous - current)
        } if previous is not None else {},
        "variants": {
            "base_count": len(current),
            "sub_count": len(alternate) if alternate is not None else None,
            "shared_count": len(current & alternate) if alternate is not None else None,
            "base_only_count": len(current - alternate) if alternate is not None else None,
            "sub_only_count": len(alternate - current) if alternate is not None else None,
        },
    }
    return result


def catalog_proxy_churn(docs_dir: Path, report: dict[str, Any]) -> None:
    """Publish on-demand churn evidence as a cataloged, credential-free JSON."""
    directory = docs_dir / "artifacts" / "quality"
    directory.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(report, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    filename = "proxy-churn.json"
    (directory / filename).write_bytes(blob)
    catalog_path = docs_dir / "catalog.json"
    if not catalog_path.is_file():
        return
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = catalog.get("files")
    if not isinstance(entries, list):
        raise ValueError("Dashboard catalog is missing its entries")
    rel = "artifacts/quality/proxy-churn.json"
    if not any(row.get("path") == rel for row in entries):
        entries.append({
            "filename": filename, "path": rel, "size": len(blob),
            "size_str": _format_size(len(blob)),
            "media_type": "application/json",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "tags": ["quality", "churn", "reconciliation"],
            "section": "quality", "type": "JSON", "ext": "JSON",
            "description": "Connection changes; a missing node is not necessarily dead",
        })
        catalog["files"] = entries
        catalog["total_files"] = len(entries)
        catalog["total_size"] = int(catalog.get("total_size") or 0) + len(blob)
        catalog["total_size_str"] = _format_size(catalog["total_size"])
        catalog_path.write_text(
            json.dumps(catalog, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )


def sync_dashboard_fallback_catalog(docs_dir: Path) -> None:
    """Align the bundled fallback after cumulative dev metadata is appended."""
    source = docs_dir / "catalog.json"
    module = docs_dir / "assets" / "js" / "data.js"
    if not module.is_file():
        return
    catalog = json.loads(source.read_text(encoding="utf-8"))
    body = module.read_text(encoding="utf-8")
    prefix = "export const FALLBACK_CATALOG = "
    suffix = ";\n\nexport const SAMPLE_PROXIES = "
    if body.count(prefix) != 1:
        raise ValueError("dashboard fallback catalog declaration is missing or duplicated")
    before, rest = body.split(prefix, 1)
    if suffix not in rest:
        raise ValueError("dashboard fallback catalog is missing its terminator")
    _, after = rest.split(suffix, 1)
    encoded = json.dumps(catalog, separators=(",", ":"), ensure_ascii=True)
    updated = before + prefix + encoded + suffix + after
    stats_prefix = "export const INGEST_STATS = "
    if updated.count(stats_prefix) != 1:
        raise ValueError("dashboard fallback telemetry declaration is missing or duplicated")
    stats_before, stats_source = updated.split(stats_prefix, 1)
    stats, consumed = json.JSONDecoder().raw_decode(stats_source)
    if not isinstance(stats, dict):
        raise ValueError("dashboard fallback telemetry must be a JSON object")
    history = docs_dir / "artifacts" / "dev" / "proxies.json"
    if history.is_file():
        historical = json.loads(history.read_text(encoding="utf-8"))
        count = historical.get("_count") if isinstance(historical, dict) else None
        if type(count) is int and count >= 0:
            stats["total_cumulative_nodes"] = count
    stats["total_published_files"] = catalog["total_files"]
    stats["total_storage_bytes"] = catalog["total_size"]
    stats["total_storage_str"] = catalog["total_size_str"]
    encoded_stats = json.dumps(stats, separators=(",", ":"), ensure_ascii=True)
    module.write_text(
        stats_before + stats_prefix + encoded_stats + stats_source[consumed:],
        encoding="utf-8",
    )


def write_main_sync_inventory(destination: Path) -> None:
    managed: list[str] = []
    for name in ("outputs", "outputs_dev", "docs"):
        directory = destination / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                relative = path.relative_to(destination).as_posix()
                if relative == "outputs_dev/_manifest.json":
                    continue
                if relative.startswith(("outputs_dev/", "docs/artifacts/dev/")) and path.name in {
                    "proxies.json", "proxies.txt", "proxies_b64sub.txt"
                }:
                    continue
                managed.append(relative)
    if not managed:
        raise ValueError("generated snapshot has no main-sync output files")
    (destination / "manifests" / "main-sync-files.txt").write_text(
        "\n".join(managed) + "\n",
        encoding="utf-8",
    )


def write_snapshot_digest(destination: Path) -> None:
    digest = hashlib.sha256()
    for path in sorted(destination.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest.update(path.relative_to(destination).as_posix().encode())
            digest.update(path.read_bytes())
    (destination / "manifests" / "SHA256SUMS").write_text(
        digest.hexdigest() + "\n",
        encoding="utf-8",
    )


def assemble_snapshot(
    checkpoint_root: Path,
    dist_root: Path,
    logs_root: Path,
    destination: Path,
    run_id: str,
    run_attempt: str,
    head_sha: str,
    head_branch: str,
    source_created_at: str,
    previous_snapshot_root: Path | None = None,
    legacy_dev_root: Path | None = None,
    dashboard_root: Path | None = None,
    shell_root: Path | None = None,
) -> dict[str, Any]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    dist = first_dir(dist_root, "dist") or dist_root
    current_outputs = require_nonempty_tree(first_dir(checkpoint_root, "outputs"), "outputs")
    current_dev = first_dir(checkpoint_root, "outputs_dev")

    copy_tree(dist, destination / "dist")
    copy_tree(current_outputs, destination / "outputs")
    retire_legacy_derivatives(destination / "outputs")
    if current_dev is not None:
        copy_tree(current_dev, destination / "outputs_dev")

    previous_dev = None
    if previous_snapshot_root is not None and previous_snapshot_root.exists():
        previous_dev = first_dir(previous_snapshot_root, "outputs_dev")
    previous_manifest = load_dev_manifest(previous_dev / "_manifest.json" if previous_dev else None)
    legacy_manifest = load_legacy_dev_identities(legacy_dev_root)
    current_manifest = load_dev_manifest(current_dev / "_manifest.json" if current_dev else None)

    cumulative_manifest = seed_missing_identities(previous_manifest, legacy_manifest)
    cumulative_manifest = merge_dev_manifests(cumulative_manifest, current_manifest)
    write_dev_outputs(destination / "outputs_dev", cumulative_manifest, source_created_at)

    dashboard_file_count = 0
    if dashboard_root is not None:
        if not dashboard_root.is_dir():
            raise ValueError(f"missing dashboard data directory: {dashboard_root}")
        # Stage the complete application shell before overlaying current-run data.
        # Copying data-only dashboard_root used to silently strip JS/CSS/PWA
        # assets from the final Pages artifact.
        if shell_root is not None:
            if not shell_root.is_dir():
                raise ValueError(f"missing dashboard shell directory: {shell_root}")
            copy_tree(shell_root, destination / "docs")
        copy_tree(dashboard_root, destination / "docs")
        retire_dashboard_derivatives(destination / "docs")
        dev_artifacts = destination / "docs" / "artifacts" / "dev"
        dev_artifacts.mkdir(parents=True, exist_ok=True)
        for name in ("proxies.json", "proxies.txt", "proxies_b64sub.txt"):
            source = destination / "outputs_dev" / name
            if source.is_file():
                shutil.copy2(source, dev_artifacts / name)
        if shell_root is not None:
            if not shell_root.is_dir():
                raise ValueError(f"missing dashboard shell directory: {shell_root}")
            # The assembled shell must never shadow verified current-run
            # telemetry. Dashboard data.js is produced from this run and
            # later reconciled to the appended cumulative catalog.
            (destination / "docs" / "assets" / "js" / "bundle.js").unlink(missing_ok=True)
        _catalog_dev_trio(destination / "docs", destination / "docs" / "artifacts" / "dev")
        sync_dashboard_fallback_catalog(destination / "docs")
        if shell_root is not None:
            _refresh_frontend_index(destination)
        dashboard_file_count = sum(1 for p in (destination / "docs").rglob("*") if p.is_file())

    logs = first_dir(logs_root, "logs") or logs_root
    summary = next(logs.rglob("run-summary.json"), None)
    if summary:
        (destination / "run-summary").mkdir(exist_ok=True)
        shutil.copy2(summary, destination / "run-summary" / "run-summary.json")

    manifests = destination / "manifests"
    manifests.mkdir(exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": 3,
        "source_run_id": run_id,
        "source_run_attempt": int(run_attempt),
        "source_commit": head_sha,
        "source_branch": head_branch,
        "source_created_at": source_created_at,
        "outputs_scope": "source_run",
        "outputs_dev_scope": "all_time_cumulative",
        "outputs_dev_previous_count": len(previous_manifest),
        "outputs_dev_legacy_count": len(legacy_manifest),
        "outputs_dev_current_count": len(current_manifest),
        "outputs_dev_cumulative_count": len(cumulative_manifest),
        "dashboard_file_count": dashboard_file_count,
    }
    (manifests / "publication.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    (destination / "README.md").write_text(
        "# HUNTX generated outputs\n\n"
        "`outputs/` contains the verified source run. `outputs_dev/` is merged "
        "with all previously published and legacy cumulative proxy identities. "
        "Do not edit manually.\n",
        encoding="utf-8",
    )
    write_main_sync_inventory(destination)
    write_snapshot_digest(destination)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--dist-root", type=Path, required=True)
    parser.add_argument("--logs-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--previous-snapshot-root", type=Path)
    parser.add_argument("--legacy-dev-root", type=Path)
    parser.add_argument("--dashboard-root", type=Path)
    parser.add_argument("--shell-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--head-branch", required=True)
    parser.add_argument("--source-created-at", required=True)
    args = parser.parse_args()

    payload = assemble_snapshot(
        checkpoint_root=args.checkpoint_root,
        dist_root=args.dist_root,
        logs_root=args.logs_root,
        destination=args.destination,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        head_sha=args.head_sha,
        head_branch=args.head_branch,
        source_created_at=args.source_created_at,
        previous_snapshot_root=args.previous_snapshot_root,
        legacy_dev_root=args.legacy_dev_root,
        dashboard_root=args.dashboard_root,
        shell_root=args.shell_root,
    )
    print(
        "Assembled generated snapshot: "
        f"run={payload['source_run_id']}/{payload['source_run_attempt']} "
        f"previous_dev={payload['outputs_dev_previous_count']} "
        f"legacy_dev={payload['outputs_dev_legacy_count']} "
        f"current_dev={payload['outputs_dev_current_count']} "
        f"cumulative_dev={payload['outputs_dev_cumulative_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
