from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..store.release_manifest import verify_release_manifest
from ..utils.atomic import atomic_write
from ..utils.safe_names import safe_component

logger = logging.getLogger(__name__)

OUTPUT_OWNERSHIP_MANIFEST = ".huntx-output-ownership.json"
_OUTPUT_OWNERSHIP_SCHEMA = 1
EMPTY_RELEASE_ARTIFACT = "empty-release.json"
_EMPTY_RELEASE_PAYLOAD = {
    "schema_version": 1,
    "status": "success",
    "record_count": 0,
    "reason": "no_eligible_records",
}


def output_filename(route: str, fmt: str) -> str:
    """Return the canonical generated filename for one route/format identity."""
    safe_route = safe_component(route, default="route")
    if fmt.endswith(".decoded.json"):
        base = safe_component(fmt.removesuffix(".decoded.json"), default="decoded")
        return f"{safe_route}_{base}_decoded.json"
    if fmt.endswith(".raw.txt"):
        base = safe_component(fmt.removesuffix(".raw.txt"), default="raw")
        return f"{safe_route}_{base}_raw.txt"
    if fmt.endswith(".singbox.json"):
        base = safe_component(fmt.removesuffix(".singbox.json"), default="singbox")
        return f"{safe_route}_{base}_singbox.json"
    if fmt.endswith(".xray.json"):
        base = safe_component(fmt.removesuffix(".xray.json"), default="xray")
        return f"{safe_route}_{base}_xray.json"
    if fmt.endswith(".nekobox.json"):
        base = safe_component(fmt.removesuffix(".nekobox.json"), default="nekobox")
        return f"{safe_route}_{base}_nekobox.json"
    if fmt.endswith(".b64sub"):
        base = safe_component(fmt.removesuffix(".b64sub"), default="b64sub")
        return f"{safe_route}_{base}_b64sub.txt"
    return f"{safe_route}.{safe_component(fmt, default='fmt')}"


def configured_output_identities(config: Any) -> dict[str, dict[str, str]]:
    """Map exact generated filenames to their configured route/format owners."""
    identities: dict[str, dict[str, str]] = {}
    for route in config.routes:
        for fmt in route.formats:
            filename = output_filename(str(route.name), str(fmt))
            owner = {"route": str(route.name), "format": str(fmt)}
            prior = identities.get(filename)
            if prior is not None and prior != owner:
                raise ValueError(
                    f"Configured outputs collide on filename {filename!r}: "
                    f"{prior['route']}:{prior['format']} vs {owner['route']}:{owner['format']}"
                )
            identities[filename] = owner
    return identities


def _safe_owned_name(name: Any) -> str | None:
    if not isinstance(name, str) or not name or name == OUTPUT_OWNERSHIP_MANIFEST:
        return None
    candidate = Path(name)
    if candidate.name != name or candidate.is_absolute() or name in {".", ".."}:
        return None
    return name


def _load_manifest(path: Path) -> dict[str, dict[str, str]] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[Export] Invalid ownership manifest ignored: %s", exc)
        return {}
    if not isinstance(value, dict) or value.get("schema_version") != _OUTPUT_OWNERSHIP_SCHEMA:
        logger.warning("[Export] Unsupported ownership manifest ignored")
        return {}
    files = value.get("files")
    if not isinstance(files, dict):
        logger.warning("[Export] Ownership manifest has invalid files object")
        return {}

    owned: dict[str, dict[str, str]] = {}
    for raw_name, raw_owner in files.items():
        name = _safe_owned_name(raw_name)
        if name is None or not isinstance(raw_owner, dict):
            continue
        route = raw_owner.get("route")
        fmt = raw_owner.get("format")
        if isinstance(route, str) and route and isinstance(fmt, str) and fmt:
            owned[name] = {"route": route, "format": fmt}
    return owned


def _bootstrap_owned_files(out_dir: Path, config: Any) -> dict[str, dict[str, str]]:
    """Safely adopt only exact current route/format outputs on first manifest run."""
    expected = configured_output_identities(config)
    return {
        name: owner
        for name, owner in expected.items()
        if (out_dir / name).is_file()
    }


def export_owned_outputs(orchestrator: Any, all_build_results: list[Any]) -> None:
    """Export outputs and prune stale files using exact manifest ownership.

    Only files explicitly owned by a previous manifest (or exact current
    route/format matches during one-time migration) are eligible for deletion.
    Unrelated files in the output directory are never inferred from prefixes.
    Call only after every route succeeds: an empty result list is an intentional
    empty snapshot, not an ingestion/build failure. Caught filesystem failures
    restore the previous snapshot; process-crash recovery requires caller staging.
    """
    out_dir = orchestrator.paths.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / OUTPUT_OWNERSHIP_MANIFEST

    prior_owned = _load_manifest(manifest_path)
    if prior_owned is None:
        prior_owned = _bootstrap_owned_files(out_dir, orchestrator.config)

    payloads: dict[str, tuple[Any, dict[str, str]]] = {}
    for result in all_build_results:
        if not isinstance(result, dict):
            raise ValueError("Malformed build result: expected an artifact object")
        route = result.get("route_name")
        fmt = result.get("format")
        data = result.get("data")
        if not isinstance(route, str) or not route or not isinstance(fmt, str) or not fmt or not data:
            raise ValueError("Malformed build result: route, format and nonempty data are required")
        filename = output_filename(route, fmt)
        if filename == EMPTY_RELEASE_ARTIFACT:
            raise ValueError("Build result collides with the reserved empty-release artifact")
        owner = {"route": route, "format": fmt}
        prior = payloads.get(filename)
        if prior is not None and prior[1] != owner:
            raise RuntimeError(
                f"Build results collide on generated filename {filename!r}: "
                f"{prior[1]} vs {owner}"
            )
        payloads[filename] = (data, owner)

    generated_at = getattr(orchestrator, "_release_generated_at", None) or datetime.now(timezone.utc).isoformat()
    metadata = {"generated_at": generated_at}
    window_start = getattr(orchestrator, "_release_window_start", None)
    if window_start is not None:
        metadata["min_ingested_at"] = window_start

    if not payloads:
        marker_path = out_dir / EMPTY_RELEASE_ARTIFACT
        if marker_path.exists() and EMPTY_RELEASE_ARTIFACT not in prior_owned:
            raise RuntimeError("Refusing to replace an unowned empty-release artifact")
        payloads[EMPTY_RELEASE_ARTIFACT] = (
            json.dumps({**_EMPTY_RELEASE_PAYLOAD, **metadata}, indent=2, sort_keys=True).encode("utf-8") + bytes([10]),
            {"route": "_release", "format": "empty"},
        )

    next_owned = {name: owner for name, (_, owner) in payloads.items()}
    manifest = {
        **metadata,
        "schema_version": _OUTPUT_OWNERSHIP_SCHEMA,
        "files": {name: next_owned[name] for name in sorted(next_owned)},
    }
    writes = {
        name: data if isinstance(data, bytes) else str(data).encode("utf-8")
        for name, (data, _) in payloads.items()
    }
    writes[OUTPUT_OWNERSHIP_MANIFEST] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    stale = sorted(set(prior_owned) - set(payloads))
    affected = sorted(set(writes) | set(stale))

    # Prepare every payload and backup before mutating the current snapshot.
    # A per-file journal restores overwritten and pruned files on caught failure.
    with tempfile.TemporaryDirectory(prefix=".output-export-", dir=out_dir.parent) as temp:
        staging = Path(temp)
        prepared = staging / "prepared"
        backup = staging / "backup"
        prepared.mkdir()
        backup.mkdir()
        for name in affected:
            target = out_dir / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise RuntimeError(f"Output target is not a regular file: {name}")
            if target.exists():
                shutil.copy2(target, backup / name)
        for name, payload in writes.items():
            atomic_write(prepared / name, payload)

        touched: list[str] = []
        try:
            for name in sorted(payloads):
                touched.append(name)
                os.replace(prepared / name, out_dir / name)
            for name in stale:
                if (out_dir / name).exists():
                    touched.append(name)
                    (out_dir / name).unlink()
            touched.append(OUTPUT_OWNERSHIP_MANIFEST)
            os.replace(prepared / OUTPUT_OWNERSHIP_MANIFEST, manifest_path)
        except Exception:
            for name in reversed(touched):
                saved = backup / name
                if saved.exists():
                    os.replace(saved, out_dir / name)
                else:
                    (out_dir / name).unlink(missing_ok=True)
            raise

    logger.info(
        "[Export] Exported %s owned file(s) to %s (%.1f KB total)",
        len(payloads),
        out_dir,
        sum(len(payload) for name, payload in writes.items() if name != OUTPUT_OWNERSHIP_MANIFEST) / 1024,
    )


def is_explicit_empty_release(root: Path, manifest: dict[str, Any]) -> bool:
    """Verify integrity, then distinguish an intentional empty release from failure."""
    verify_release_manifest(root, manifest)
    artifacts = manifest["artifacts"]
    if not any(entry["path"] == EMPTY_RELEASE_ARTIFACT for entry in artifacts):
        return False
    if len(artifacts) != 1:
        raise ValueError("Empty-release marker cannot accompany data artifacts")
    value = json.loads((root / EMPTY_RELEASE_ARTIFACT).read_text(encoding="utf-8"))
    required = set(_EMPTY_RELEASE_PAYLOAD) | {"generated_at"}
    if not isinstance(value, dict) or set(value) not in (required, required | {"min_ingested_at"}):
        raise ValueError("Invalid empty-release marker fields")
    for key, expected in _EMPTY_RELEASE_PAYLOAD.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise ValueError(f"Invalid empty-release marker field: {key}")

    def timestamp(key: str) -> datetime:
        raw = value[key]
        if not isinstance(raw, str) or "T" not in raw:
            raise ValueError(f"Invalid empty-release timestamp: {key}")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid empty-release timestamp: {key}") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"Empty-release timestamp requires timezone: {key}")
        return parsed

    generated = timestamp("generated_at")
    if "min_ingested_at" in value and timestamp("min_ingested_at") > generated:
        raise ValueError("Empty-release window starts after generation")
    return True
