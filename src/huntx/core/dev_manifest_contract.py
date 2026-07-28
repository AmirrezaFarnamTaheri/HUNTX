from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Type

from ..formats.npvt import strip_proxy_remark
from ..utils.atomic import atomic_write

logger = logging.getLogger(__name__)


def _normalise_manifest_value(value: Any) -> float | int | str:
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
    try:
        return float(candidate) < float(existing)
    except (TypeError, ValueError):
        return str(candidate) < str(existing)


def install_dev_manifest_contract(orchestrator_type: Type[Any]) -> None:
    if getattr(orchestrator_type, "_dev_manifest_contract_applied", False):
        return
    original = orchestrator_type._export_dev_outputs

    def hardened_export_dev_outputs(self: Any, all_build_results: list[Any]) -> None:
        normalise_dev_manifest(self.paths.dev_output_dir / "_manifest.json")
        original(self, all_build_results)

    orchestrator_type._export_dev_outputs = hardened_export_dev_outputs  # type: ignore[method-assign]
    orchestrator_type._dev_manifest_contract_applied = True  # type: ignore[attr-defined]
