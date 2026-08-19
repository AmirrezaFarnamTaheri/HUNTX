from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Type

from ..formats.npvt import strip_proxy_remark
from ..utils.atomic import atomic_write

logger = logging.getLogger(__name__)


def _normalise_manifest_value(value: Any) -> float | int | str:
    """Accept only scalar persisted first-seen values."""
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return value
    raise ValueError("dev manifest timestamps must be scalar values")


def normalise_dev_manifest(path: Path) -> dict[str, float | int | str]:
    """Canonicalise persisted proxy identities before cumulative export.

    Historical manifests may contain clean remarks or pre-canonical VMess JSON.
    Collisions are merged by preserving the earliest first-seen value so an
    upgrade cannot reset age ordering or retain duplicate logical proxies.
    """

    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[DevExport] Could not read manifest, starting fresh: %s", exc)
        return {}
    if not isinstance(raw, dict):
        logger.warning("[DevExport] Manifest root is not an object, starting fresh")
        return {}

    normalised: dict[str, float | int | str] = {}
    changed = False
    for raw_uri, raw_first_seen in raw.items():
        if not isinstance(raw_uri, str):
            changed = True
            continue
        uri = strip_proxy_remark(raw_uri.strip())
        if not uri or "://" not in uri:
            changed = True
            continue
        try:
            first_seen = _normalise_manifest_value(raw_first_seen)
        except ValueError:
            changed = True
            continue
        previous = normalised.get(uri)
        if previous is None or _earlier(first_seen, previous):
            normalised[uri] = first_seen
        if uri != raw_uri or previous is not None:
            changed = True

    if changed or normalised != raw:
        atomic_write(
            path,
            json.dumps(normalised, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
    return normalised


def _earlier(candidate: float | int | str, existing: float | int | str) -> bool:
    """Compare first-seen values while tolerating legacy string timestamps."""
    try:
        return float(candidate) < float(existing)
    except (TypeError, ValueError):
        return str(candidate) < str(existing)


def _eligible_manifest_uris(orchestrator: Any) -> set[str]:
    """Return canonical proxy URIs still attributable to approved sources.

    The historic dev manifest was append-only and therefore kept publishing a
    URI after its source was quarantined/retired.  Trust revocation must be
    reflected in generated outputs as well as new route builds.  We derive the
    allow-set from current active records belonging to publication-eligible
    sources; if eligibility cannot be proven, the URI is removed.
    """
    sources = [
        source
        for source in getattr(orchestrator.config, "sources", [])
        if getattr(source, "publication_eligible", True)
    ]
    source_ids = [str(source.id) for source in sources if getattr(source, "id", None)]
    if not source_ids:
        return set()

    records = orchestrator.repo.get_records_for_build(
        ["npvt", "npvtsub"],
        source_ids,
    )
    allowed: set[str] = set()
    for record in records:
        data = record.get("data") if isinstance(record, dict) else None
        if not isinstance(data, dict):
            continue
        line = data.get("line")
        if not isinstance(line, str):
            continue
        uri = strip_proxy_remark(line.strip())
        if uri and "://" in uri:
            allowed.add(uri)
    return allowed


def prune_dev_manifest_to_eligible_sources(
    orchestrator: Any,
    path: Path,
) -> dict[str, float | int | str]:
    """Remove manifest entries that no approved active source can justify."""
    manifest = normalise_dev_manifest(path)
    if not manifest:
        return manifest

    allowed = _eligible_manifest_uris(orchestrator)
    pruned = {uri: first_seen for uri, first_seen in manifest.items() if uri in allowed}
    removed = len(manifest) - len(pruned)
    if removed:
        logger.warning(
            "[DevExport] Revoked %s manifest URI(s) no longer backed by approved sources",
            removed,
        )
        atomic_write(
            path,
            json.dumps(pruned, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
    return pruned


def install_dev_manifest_contract(orchestrator_type: Type[Any]) -> None:
    """Install canonicalization and trust-revocation around dev export once."""
    if getattr(orchestrator_type, "_dev_manifest_contract_applied", False):
        return
    original = orchestrator_type._export_dev_outputs

    def hardened_export_dev_outputs(self: Any, all_build_results: list[Any]) -> None:
        manifest_path = self.paths.dev_output_dir / "_manifest.json"
        prune_dev_manifest_to_eligible_sources(self, manifest_path)
        original(self, all_build_results)
        # Re-run after export so a future change to the original implementation
        # cannot reintroduce entries from unapproved sources via config drift.
        prune_dev_manifest_to_eligible_sources(self, manifest_path)

        # If trust revocation emptied the manifest, remove stale rendered views
        # instead of leaving previously published proxy material on disk.
        manifest = normalise_dev_manifest(manifest_path)
        if not manifest:
            for name in ("proxies.txt", "proxies.json", "proxies_b64sub.txt"):
                candidate = self.paths.dev_output_dir / name
                try:
                    candidate.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("[DevExport] Could not remove stale %s: %s", name, exc)

    orchestrator_type._export_dev_outputs = hardened_export_dev_outputs  # type: ignore[method-assign]
    orchestrator_type._dev_manifest_contract_applied = True  # type: ignore[attr-defined]
