#!/usr/bin/env python3
"""Fail-closed current-run release gate and immutable publication receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"missing or invalid release evidence: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("release evidence must be a JSON object")
    return payload


def check_health(path: Path, runtime_exit_code: int) -> dict[str, Any]:
    if type(runtime_exit_code) is not int or runtime_exit_code != 0:
        raise ValueError("runtime did not exit successfully")
    summary = read_object(path).get("summary")
    if not isinstance(summary, dict) or summary.get("release_eligible") is not True:
        raise ValueError("current run did not explicitly authorize a release")
    return summary


def release_manifest(dist: Path) -> dict[str, Any]:
    from huntx.store.release_manifest import verify_release_manifest

    manifest = read_object(dist / "manifest.json")
    verify_release_manifest(dist, manifest)
    return manifest


def check_empty_release(dist: Path) -> bool:
    from huntx.core.output_ownership import is_explicit_empty_release

    return is_explicit_empty_release(dist, release_manifest(dist))


def timestamp(value: Any) -> str:
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise ValueError("release timestamp must be a timezone-aware ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("release timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def build_receipt(dist: Path, summary: dict[str, Any], run_id: str, run_attempt: str) -> dict[str, Any]:
    if not run_id.isdecimal() or not run_attempt.isdecimal() or int(run_id) <= 0 or int(run_attempt) <= 0:
        raise ValueError("positive source run ID and attempt are required")
    empty = check_empty_release(dist)
    generated_at = datetime.now(timezone.utc).isoformat()
    if empty:
        generated_at = timestamp(read_object(dist / "empty-release.json")["generated_at"])
    return {
        "schema_version": 1,
        "source_run_id": run_id,
        "source_run_attempt": run_attempt,
        "runtime_exit_code": 0,
        "release_eligible": True,
        "package_source": "current",
        "generated_at": generated_at,
        "min_ingested_at": summary.get("min_ingested_at"),
        "empty_release": empty,
        "manifest_sha256": hashlib.sha256((dist / "manifest.json").read_bytes()).hexdigest(),
    }


def verify_receipt(path: Path, dist: Path, run_id: str, run_attempt: str) -> dict[str, Any]:
    receipt = read_object(path)
    if (
        type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
        or receipt.get("source_run_id") != run_id
        or receipt.get("source_run_attempt") != run_attempt
        or receipt.get("package_source") != "current"
        or receipt.get("release_eligible") is not True
        or type(receipt.get("runtime_exit_code")) is not int
        or receipt["runtime_exit_code"] != 0
    ):
        raise ValueError("release receipt does not authorize this source run and attempt")
    timestamp(receipt.get("generated_at"))
    empty = check_empty_release(dist)
    if receipt.get("empty_release") is not empty:
        raise ValueError("release receipt empty status does not match verified dist")
    digest = hashlib.sha256((dist / "manifest.json").read_bytes()).hexdigest()
    if receipt.get("manifest_sha256") != digest:
        raise ValueError("release receipt does not match the dist manifest")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--health", type=Path)
    mode.add_argument("--verify-receipt", type=Path)
    mode.add_argument("--empty-release", action="store_true")
    parser.add_argument("--runtime-exit-code", type=int, default=1)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-attempt", default="")
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.empty_release:
            if args.dist is None or not check_empty_release(args.dist):
                raise ValueError("not a verified explicit empty release")
            return 0
        if args.verify_receipt:
            if args.dist is None:
                raise ValueError("receipt verification requires --dist")
            receipt = verify_receipt(args.verify_receipt, args.dist, args.run_id, args.run_attempt)
        else:
            summary = check_health(args.health, args.runtime_exit_code)
            if args.receipt is None:
                return 0
            if args.dist is None:
                raise ValueError("receipt creation requires --dist")
            receipt = build_receipt(args.dist, summary, args.run_id, args.run_attempt)
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a", encoding="utf-8") as handle:
                handle.write(f"generated_at={receipt['generated_at']}\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(f"Release gate blocked publication: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
