#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

_TIMEOUT_EXIT_CODES = {124, 137, 143}
_METRIC_KEYS = (
    "total_artifacts",
    "ingest_ok",
    "ingest_err",
    "failed_routes",
    "publish_attempts",
    "publish_failures",
    "publish_pending",
    "publish_cancelled",
    "build_pending",
    "build_cancelled",
    "ingestion_cancelled",
    "lifo_pages_processed",
    "lifo_windows_completed",
    "lifo_window_failures",
    "ingestion_budget_exhausted",
    "timed_out_stage",
)


def _load_report(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "run-health report was not created"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"run-health report is unreadable: {exc}"
    if not isinstance(payload, dict):
        return None, "run-health report root must be a JSON object"
    return payload, None


def _fallback_disposition(exit_code: int, checkpoint_ready: bool) -> tuple[str, list[str]]:
    if exit_code == 0:
        return "success", ["runtime exited successfully without a structured report"]
    if exit_code in _TIMEOUT_EXIT_CODES and checkpoint_ready:
        return "degraded", ["watchdog interrupted runtime after a recoverable checkpoint"]
    return "fatal", [f"runtime exited with code {exit_code} without a trustworthy structured report"]


def _write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _append_step_summary(markdown: str, explicit_path: str | None) -> None:
    path = explicit_path or os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def _inventory(data_dir: Path) -> list[tuple[str, int]]:
    if not data_dir.exists():
        return []
    rows: list[tuple[str, int]] = []
    for path in sorted(data_dir.rglob("*")):
        if path.is_file():
            try:
                rows.append((str(path.relative_to(data_dir)), path.stat().st_size))
            except OSError:
                continue
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HuntX runtime health for GitHub Actions")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-ready", default="false")
    parser.add_argument("--package-ready", default="false")
    parser.add_argument("--step-summary")
    args = parser.parse_args()

    checkpoint_ready = args.checkpoint_ready.strip().lower() == "true"
    package_ready = args.package_ready.strip().lower() == "true"
    payload, load_error = _load_report(args.summary)

    if payload is not None:
        disposition = str(payload.get("disposition", "fatal")).strip().lower()
        status = str(payload.get("status", "unknown"))
        reasons = [str(value) for value in payload.get("reasons", [])]
        metrics = payload.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
    else:
        disposition, reasons = _fallback_disposition(args.exit_code, checkpoint_ready)
        status = "missing-report"
        metrics = {}
        if load_error:
            reasons.insert(0, load_error)

    if disposition not in {"success", "degraded", "fatal"}:
        reasons.insert(0, f"invalid disposition {disposition!r}")
        disposition = "fatal"

    annotation = "notice"
    if disposition == "degraded":
        annotation = "warning"
    elif disposition == "fatal":
        annotation = "error"
    message = "; ".join(reasons) or "no degradation detected"
    print(f"::{annotation} title=HuntX {disposition}::{message}")

    print("HUNTX_RUNTIME_DIAGNOSTICS_BEGIN")
    print(f"disposition={disposition}")
    print(f"status={status}")
    print(f"exit_code={args.exit_code}")
    print(f"checkpoint_ready={str(checkpoint_ready).lower()}")
    print(f"package_ready={str(package_ready).lower()}")
    print(f"summary_present={str(payload is not None).lower()}")
    for key in _METRIC_KEYS:
        print(f"metric.{key}={metrics.get(key, '')}")
    for index, reason in enumerate(reasons, start=1):
        print(f"reason.{index}={reason}")

    inventory = _inventory(args.data_dir)
    print(f"inventory.files={len(inventory)}")
    print(f"inventory.bytes={sum(size for _, size in inventory)}")
    for name, size in inventory[:200]:
        print(f"inventory.item={size}\t{name}")
    if len(inventory) > 200:
        print(f"inventory.truncated={len(inventory) - 200}")
    print("HUNTX_RUNTIME_DIAGNOSTICS_END")

    metric_rows = "\n".join(f"| `{key}` | `{metrics.get(key, '')}` |" for key in _METRIC_KEYS)
    reason_rows = "\n".join(f"- `{reason}`" for reason in reasons) or "- None"
    markdown = f"""## HuntX runtime health

| Field | Value |
|---|---|
| Disposition | **{disposition}** |
| Runtime status | `{status}` |
| Process exit code | `{args.exit_code}` |
| Checkpoint ready | `{str(checkpoint_ready).lower()}` |
| Package ready | `{str(package_ready).lower()}` |
| Structured report | `{str(payload is not None).lower()}` |

### Reasons
{reason_rows}

### Metrics
| Metric | Value |
|---|---|
{metric_rows}

### Artifact inventory
- Files: `{len(inventory)}`
- Bytes: `{sum(size for _, size in inventory)}`
"""
    _append_step_summary(markdown, args.step_summary)

    _write_output("disposition", disposition)
    _write_output("summary_present", str(payload is not None).lower())
    _write_output("status", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
