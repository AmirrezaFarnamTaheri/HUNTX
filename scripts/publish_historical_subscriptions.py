#!/usr/bin/env python3
"""Publish the already-public historical per-protocol latest feeds without a new release.

This path never creates a new verified proxy release. It starts from an
immutable, SHA256-sealed generated-outputs snapshot and its cumulative manifest;
the original source-run receipt, release artifacts and telemetry stay untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from scripts.assemble_generated_snapshot import (
    _catalog_dev_trio,
    catalog_latest_subscriptions,
    load_dev_manifest,
    rebuild_aggregate_artifact_manifest,
    verify_snapshot_digest,
    write_dev_outputs,
    write_snapshot_digest,
)
from huntx.formats.latest_subscriptions import (
    validate_latest_subscriptions,
    write_latest_subscriptions,
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHELL = (
    "subscriptions.html",
    "assets/js/subscription-library.js",
    "assets/css/subscription-library.css",
)
_NAV_LINK = (
    '      <a href="subscriptions.html" '
    'class="px-3.5 py-2 rounded-xl text-xs font-mono font-semibold '
    'border border-cyan-700 text-cyan-300 hover:text-white focus-ring" '
    'style="white-space:nowrap" aria-label="Historical latest subscriptions">'
    'Latest feeds ↗</a>\n'
)
_NAV_ANCHOR = '      <a href="network-doctor.html"'


def _require_receipt(root: Path) -> dict[str, Any]:
    path = root / "manifests" / "publication.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("missing verified previous publication receipt") from exc
    if not isinstance(receipt, dict):
        raise ValueError("invalid previous publication receipt")
    if (
        not str(receipt.get("source_run_id", "")).isdigit()
        or not isinstance(receipt.get("source_run_attempt"), int)
        or receipt["source_run_attempt"] < 1
        or not isinstance(receipt.get("source_created_at"), str)
        or not receipt["source_created_at"]
        or not isinstance(receipt.get("source_commit"), str)
        or not _COMMIT_RE.fullmatch(receipt["source_commit"])
        or receipt.get("outputs_scope") != "source_run"
        or receipt.get("outputs_dev_scope") != "all_time_cumulative"
    ):
        raise ValueError("untrusted previous publication receipt")
    return receipt


def prepare_historical_pages(
    previous_root: Path,
    main_docs_root: Path,
    destination: Path,
    control_commit: str,
) -> dict[str, Any]:
    """Create a sealed Pages tree from public history, preserving live releases.

    Git checkout worktrees contain an auxiliary .git FILE that does not belong
    in the previously published snapshot; omit only that Git metadata. The
    previous snapshot SHA256SUMS check is performed before editing anything.
    """
    if not isinstance(control_commit, str) or not _COMMIT_RE.fullmatch(control_commit):
        raise ValueError("invalid historical publication control commit")
    previous = previous_root.resolve()
    main_docs = main_docs_root.resolve()
    target = destination.resolve()
    if (
        not previous.is_dir() or not main_docs.is_dir()
        or target == previous or previous in target.parents
        or target == main_docs or main_docs in target.parents
        or target in previous.parents or target in main_docs.parents
    ):
        raise ValueError("unsafe historical publication source or destination")
    if target.exists():
        raise ValueError("historical publication target already exists")
    for relative in _SHELL:
        path = main_docs / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing current public subscription shell: {relative}")
    for item in previous.rglob("*"):
        if item.is_symlink():
            raise ValueError("previous verified snapshot contains symbolic links")
    shutil.copytree(previous, target, ignore=shutil.ignore_patterns(".git"))
    try:
        verify_snapshot_digest(target)
        receipt = _require_receipt(target)
        prior_created_at = receipt["source_created_at"]
        manifest_path = target / "outputs_dev" / "_manifest.json"
        compressed = manifest_path.with_name("_manifest.json.gz.index.json")
        if not manifest_path.is_file() and not compressed.is_file():
            raise ValueError("previous cumulative manifest is missing")
        identities = load_dev_manifest(manifest_path)
        if not identities:
            raise ValueError("previous cumulative manifest contains no identities")

        docs = target / "docs"
        if not docs.is_dir():
            raise ValueError("previous verified snapshot lacks docs")
        original_release = docs / "artifacts" / "release" / "manifest.json"
        original_telemetry = docs / "assets" / "js" / "data.js"
        if not original_release.is_file() or not original_telemetry.is_file():
            raise ValueError("previous verified release evidence is incomplete")
        release_bytes = original_release.read_bytes()
        telemetry_bytes = original_telemetry.read_bytes()
        prior_receipt_bytes = (target / "manifests" / "publication.json").read_bytes()

        dev = docs / "artifacts" / "dev"
        write_dev_outputs(dev, identities, prior_created_at)
        # The site only needs the historical JSON, TXT and Base64 products.
        # The authoritative compressed manifest remains under outputs_dev.
        (dev / "_manifest.json").unlink(missing_ok=True)
        (dev / "_manifest.json.gz.index.json").unlink(missing_ok=True)
        for part in dev.glob("_manifest.json.gz.part*"):
            part.unlink()
        latest = docs / "subscriptions" / "latest"
        index = write_latest_subscriptions(latest, identities, prior_created_at)
        if index["aggregate"]["count"] == 0:
            raise ValueError("no validated historical proxy records to publish")
        mirror = dev / "latest"
        if mirror.exists():
            if mirror.is_symlink() or not mirror.is_dir():
                raise ValueError("unsafe existing historical mirror")
            shutil.rmtree(mirror)
        shutil.copytree(latest, mirror)
        validate_latest_subscriptions(latest)
        validate_latest_subscriptions(mirror)

        for relative in _SHELL:
            target_file = docs / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(main_docs / relative, target_file)
        index_html = docs / "index.html"
        text = index_html.read_text(encoding="utf-8")
        if 'href="subscriptions.html"' not in text:
            if _NAV_ANCHOR not in text:
                raise ValueError("previous homepage has no safe subscription link anchor")
            index_html.write_text(
                text.replace(_NAV_ANCHOR, _NAV_LINK + _NAV_ANCHOR, 1),
                encoding="utf-8",
            )

        _catalog_dev_trio(docs, dev)
        # Rebuilding omitted public historical JSON with the current renderer
        # can change harmless remark formatting. Update ONLY its historical
        # catalog entry, never a source-run release receipt or artifact.
        catalog_path = docs / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        historical_json = (dev / "proxies.json").read_bytes()
        for entry in catalog["files"]:
            if entry.get("path") == "artifacts/dev/proxies.json":
                entry["size"] = len(historical_json)
                entry["sha256"] = hashlib.sha256(historical_json).hexdigest()
                mib = len(historical_json) / 1024 / 1024
                entry["size_str"] = f"{mib:.1f} MB"
        catalog_path.write_text(
            json.dumps(catalog, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        catalog_latest_subscriptions(docs)
        rebuild_aggregate_artifact_manifest(docs)

        # Source-run publication receipt, verified release and telemetry stay
        # exactly as published. Only historical metadata/catalog changes.
        if (
            original_release.read_bytes() != release_bytes
            or original_telemetry.read_bytes() != telemetry_bytes
            or (target / "manifests" / "publication.json").read_bytes()
            != prior_receipt_bytes
        ):
            raise ValueError("historical publication modified a verified release")
        history_receipt = {
            "schema_version": 1,
            "publication_type": "historical_only",
            "health_status": "historical_unverified",
            "control_commit": control_commit,
            "source_commit": receipt["source_commit"],
            "source_run_id": receipt["source_run_id"],
            "source_run_attempt": receipt["source_run_attempt"],
            "source_created_at": prior_created_at,
            "verified_release_preserved": True,
            "aggregate_count": index["aggregate"]["count"],
            "limit_per_protocol": index["limit_per_protocol"],
            "protocol_limits": index["protocol_limits"],
        }
        (target / "manifests" / "historical-subscriptions.json").write_text(
            json.dumps(history_receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        write_snapshot_digest(target)
        verify_snapshot_digest(target)
        return index
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-root", required=True, type=Path)
    parser.add_argument("--main-docs-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--control-commit", required=True)
    args = parser.parse_args()
    index = prepare_historical_pages(
        args.previous_root, args.main_docs_root,
        args.destination, args.control_commit,
    )
    print(
        "Verified historical subscription snapshot ready: "
        f"{len(index['protocols'])} families, "
        f"{index['aggregate']['count']} historical entries, "
        f"source {index['generated_at']}",
    )


if __name__ == "__main__":
    main()
