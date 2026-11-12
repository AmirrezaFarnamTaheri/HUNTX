#!/usr/bin/env python3
"""Write a credential-free no-release receipt from allowlisted runtime facts.

This is a diagnostic receipt, never publication authorization. Keep schema v1
fields for existing consumers and do not copy arbitrary run-summary data:
source logs may contain secrets or raw proxy subscriptions.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_STATUS = frozenset({"completed", "timed_out", "partial", "failed"})
_STAGES = frozenset({
    "ingestion", "transformation", "build", "publishing",
    "export", "cleanup",
})
_REASON_CODES = frozenset({
    "deadline_exhausted_after_recoverable_progress",
    "optional_source_failures",
    "build_work_pending",
    "no_new_artifacts",
    "telegram_retry_wait_nonblocking",
    "ingestion_budget_exhausted",
})


def _counter(value: Any) -> int:
    return value if type(value) is int and 0 <= value <= 1_000_000 else 0


def _summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_verdict(
    summary: dict[str, Any],
    *,
    run_id: str,
    run_attempt: str,
    source_commit: str,
    runtime_exit_code: int,
    package_source: str,
    checkpoint_ready: bool,
) -> dict[str, Any]:
    """Never inherit unapproved release flags or arbitrary diagnostic text."""
    if not re.fullmatch(r"[0-9]{1,24}", run_id):
        raise ValueError("invalid run ID")
    if not re.fullmatch(r"[0-9]{1,8}", run_attempt):
        raise ValueError("invalid run attempt")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("invalid source SHA")
    if package_source not in {"current", "restored", "none"}:
        raise ValueError("invalid package source")
    status = summary.get("status")
    detail = summary.get("summary")
    details = detail if isinstance(detail, dict) else {}
    metrics = summary.get("metrics")
    measurements = metrics if isinstance(metrics, dict) else {}
    stage = details.get("timed_out_stage") or measurements.get(
        "timed_out_stage"
    ) or summary.get("timed_out_stage")
    reasons = summary.get("reasons")
    safe_reasons = (
        sorted({value for value in reasons if type(value) is str and value in _REASON_CODES})
        if isinstance(reasons, list) else []
    )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "source_commit": source_commit,
        "release_published": False,
        "release_eligible": False,
        "package_ready": False,
        "package_source": package_source,
        "checkpoint_ready": checkpoint_ready,
        "runtime_exit_code": runtime_exit_code,
        "run_status": status if type(status) is str and status in _STATUS else "unknown",
        "timed_out_stage": stage if type(stage) is str and stage in _STAGES else None,
        "build_pending": _counter(details.get("build_pending", measurements.get(
            "build_pending", summary.get("build_pending")
        ))),
        "degraded_source_failures": _counter(details.get(
            "degraded_source_failures", summary.get("degraded_source_failures")
        )),
        "reasons": safe_reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runtime-exit-code", type=int, required=True)
    parser.add_argument("--package-source", required=True)
    parser.add_argument("--checkpoint-ready", choices=("true", "false"), required=True)
    args = parser.parse_args()
    result = write_verdict(
        _summary(args.summary),
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        source_commit=args.source_commit,
        runtime_exit_code=args.runtime_exit_code,
        package_source=args.package_source,
        checkpoint_ready=args.checkpoint_ready == "true",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
