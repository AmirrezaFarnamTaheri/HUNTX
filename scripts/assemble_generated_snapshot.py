#!/usr/bin/env python3
"""Assemble a verified, deterministic generated-output publication snapshot."""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ManifestValue = float | int | str
LEGACY_FIRST_SEEN = 0


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


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


def strip_proxy_remark(uri: str) -> str:
    if uri.startswith("vmess://"):
        try:
            raw = _b64_decode_safe(uri[8:])
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return uri
            payload.pop("ps", None)
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            return "vmess://" + base64.b64encode(canonical.encode()).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri
    marker = uri.rfind("#")
    return uri[:marker] if marker > 0 else uri


def add_clean_remark(uri: str, counter: dict[str, int]) -> str:
    scheme = uri.split("://", 1)[0].lower() if "://" in uri else "proxy"
    counter[scheme] = counter.get(scheme, 0) + 1
    tag = f"{scheme}-{counter[scheme]}"

    if uri.startswith("vmess://"):
        try:
            raw = _b64_decode_safe(uri[8:])
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return uri
            payload["ps"] = tag
            encoded = json.dumps(payload, separators=(",", ":")).encode()
            return "vmess://" + base64.b64encode(encoded).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri

    marker = uri.rfind("#")
    base = uri[:marker] if marker > 0 else uri
    return f"{base}#{tag}"


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
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read dev manifest {path}: {exc}") from exc
    return normalise_manifest(raw, path)


def merge_dev_manifests(
    previous: dict[str, ManifestValue],
    current: dict[str, ManifestValue],
) -> dict[str, ManifestValue]:
    merged = dict(previous)
    for uri, first_seen in current.items():
        existing = merged.get(uri)
        if existing is None or _earlier(first_seen, existing):
            merged[uri] = first_seen
    return merged


def seed_missing_identities(
    manifest: dict[str, ManifestValue],
    identity_seed: dict[str, ManifestValue],
) -> dict[str, ManifestValue]:
    seeded = dict(manifest)
    for uri, first_seen in identity_seed.items():
        seeded.setdefault(uri, first_seen)
    return seeded


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
    if manifest_path.is_file() and manifest_path.stat().st_size > 0:
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
    manifest_path = dev_dir / "_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sorted_uris = sorted(manifest)
    sorted_uris.sort(key=lambda uri: _timestamp_sort_key(manifest[uri]), reverse=True)
    remark_counter: dict[str, int] = {}
    remarked_uris = [add_clean_remark(uri, remark_counter) for uri in sorted_uris]
    timestamp = _display_timestamp(source_created_at)

    header = (
        f"# huntx proxy list — {timestamp}\n"
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


def write_main_sync_inventory(destination: Path) -> None:
    managed: list[str] = []
    for name in ("outputs", "outputs_dev", "docs"):
        directory = destination / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                managed.append(path.relative_to(destination).as_posix())
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
        copy_tree(dashboard_root, destination / "docs")
        dev_artifacts = destination / "docs" / "artifacts" / "dev"
        dev_artifacts.mkdir(parents=True, exist_ok=True)
        for name in ("proxies.json", "proxies.txt", "proxies_b64sub.txt"):
            source = destination / "outputs_dev" / name
            if source.is_file():
                shutil.copy2(source, dev_artifacts / name)
        if shell_root is not None:
            if not shell_root.is_dir():
                raise ValueError(f"missing dashboard shell directory: {shell_root}")
            for rel in ("index.html", "assets/js/bundle.js", "assets/js/data.js"):
                source_file = shell_root / rel
                if source_file.is_file():
                    target_file = destination / "docs" / rel
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target_file)
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
