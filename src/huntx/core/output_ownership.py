from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..utils.atomic import atomic_write
from ..utils.safe_names import safe_component

logger = logging.getLogger(__name__)

OUTPUT_OWNERSHIP_MANIFEST = ".huntx-output-ownership.json"
_OUTPUT_OWNERSHIP_SCHEMA = 1


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
            logger.warning("[Export] Ignoring malformed build result: %s", type(result).__name__)
            continue
        route = result.get("route_name")
        fmt = result.get("format")
        data = result.get("data")
        if not isinstance(route, str) or not route or not isinstance(fmt, str) or not fmt or not data:
            continue
        filename = output_filename(route, fmt)
        owner = {"route": route, "format": fmt}
        prior = payloads.get(filename)
        if prior is not None and prior[1] != owner:
            raise RuntimeError(
                f"Build results collide on generated filename {filename!r}: "
                f"{prior[1]} vs {owner}"
            )
        payloads[filename] = (data, owner)

    retention_days = orchestrator._output_retention_days()
    retention_cutoff = time.time() - (retention_days * 86400)
    next_owned: dict[str, dict[str, str]] = {}

    for filename, owner in prior_owned.items():
        if filename in payloads:
            continue
        path = out_dir / filename
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= retention_cutoff:
                next_owned[filename] = owner
                continue
        except OSError:
            # If metadata cannot be inspected, retain ownership rather than
            # guessing that deletion is safe.
            next_owned[filename] = owner
            continue
        try:
            path.unlink()
            logger.info("[Export] Removed stale owned output: %s", filename)
        except OSError as exc:
            next_owned[filename] = owner
            logger.warning("[Export] Could not remove stale owned output %s: %s", filename, exc)

    failures: list[str] = []
    total_bytes = 0
    for filename, (data, owner) in payloads.items():
        path = out_dir / filename
        try:
            payload = data if isinstance(data, bytes) else str(data).encode("utf-8")
            atomic_write(path, payload)
            total_bytes += path.stat().st_size
            next_owned[filename] = owner
        except Exception as exc:
            failures.append(f"{filename}: {exc}")
            logger.exception("[Export] Failed to write owned output %s", filename)

    manifest = {
        "schema_version": _OUTPUT_OWNERSHIP_SCHEMA,
        "files": {name: next_owned[name] for name in sorted(next_owned)},
    }
    atomic_write(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
    )

    logger.info(
        "[Export] Exported %s owned file(s) to %s (%.1f KB total)",
        len(payloads) - len(failures),
        out_dir,
        total_bytes / 1024,
    )
    if failures:
        raise RuntimeError("Output export failed: " + "; ".join(failures))
