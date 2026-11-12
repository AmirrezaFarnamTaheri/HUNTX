"""Emit a fail-closed, credential-free no-release evidence receipt.

The upload name and schema version stay stable for publisher consumers.
Only allowlisted health fields are copied; no source URLs, tokens, or proxy
identities are exposed in this public CI artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


_REASON = re.compile(r"^[a-z0-9_]{1,90}$")
_STATUSES = frozenset({"completed", "partial", "timed_out", "failed"})


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def create_no_release_verdict(
    summary_path: Path,
    *,
    run_id: str,
    attempt: str,
    source_commit: str,
    package_source: str,
    runtime_exit_code: str,
) -> dict[str, Any]:
    """Summarize only safe, independently attributable failure evidence."""
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("invalid source commit")
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise ValueError("invalid producer run coordinates")
    if package_source not in {"current", "restored", "none", ""}:
        raise ValueError("invalid package source")

    try:
        raw = summary_path.read_bytes()
        summary = json.loads(raw)
        if not isinstance(summary, dict):
            raise ValueError("run summary is not an object")
    except (FileNotFoundError, OSError, ValueError, UnicodeError):
        raw = None
        summary = {}

    metrics = summary.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    detail = summary.get("summary")
    detail = detail if isinstance(detail, dict) else {}

    status = summary.get("status")
    status = status if status in _STATUSES else "unavailable"
    provided_reasons = summary.get("reasons")
    if isinstance(provided_reasons, list):
        reasons = sorted({
            item for item in provided_reasons
            if isinstance(item, str) and _REASON.fullmatch(item)
        })
    else:
        reasons = []
    if status == "unavailable":
        reasons = ["runtime_summary_unavailable"]

    timeout = detail.get("timed_out_stage", metrics.get("timed_out_stage"))
    if timeout not in {"ingestion", "transformation", "build", "publishing", "export", "cleanup"}:
        timeout = None
    build_pending = _nonnegative_int(detail.get("build_pending", metrics.get("build_pending")))
    source_failures = _nonnegative_int(
        detail.get("optional_ingest_err", metrics.get("optional_ingest_err"))
    )

    try:
        code = int(runtime_exit_code)
    except ValueError:
        code = 1

    return {
        "schema_version": 1,
        "run_id": run_id,
        "run_attempt": attempt,
        "source_commit": source_commit,
        "release_published": False,
        "package_ready": False,
        "package_source": package_source,
        "runtime_exit_code": code,
        "run_status": status,
        "timed_out_stage": timeout,
        "build_pending": build_pending,
        "source_failures": source_failures,
        "reasons": reasons,
        "summary_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--package-source", required=True)
    parser.add_argument("--runtime-exit-code", required=True)
    args = parser.parse_args()

    verdict = create_no_release_verdict(
        args.summary, run_id=args.run_id, attempt=args.attempt,
        source_commit=args.source_commit,
        package_source=args.package_source,
        runtime_exit_code=args.runtime_exit_code,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        f"No release: run={verdict['run_id']}/{verdict['run_attempt']} "
        f"status={verdict['run_status']} stage={verdict['timed_out_stage']} "
        f"reasons={verdict['reasons']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
