from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


_FATAL_REASONS = {
    "invalid_configuration",
    "no_approved_sources",
    "security_violation",
    "state_corruption",
    "unrecoverable_state",
    "invariant_violation",
}


@dataclass(frozen=True)
class RunHealth:
    disposition: str
    status: str
    reasons: tuple[str, ...]
    recoverable_progress: bool
    metrics: dict[str, Any]

    @property
    def is_fatal(self) -> bool:
        return self.disposition == "fatal"


def _as_int(summary: Mapping[str, Any], key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def evaluate_run_health(
    summary: Mapping[str, Any],
    *,
    no_publish: bool = False,
) -> RunHealth:
    """Classify a run without converting isolated degradation into failure.

    A run is fatal only when configuration/state is explicitly invalid, the
    status is unknown without any recoverable progress, or execution failed
    before producing any useful state and without a recognizable external
    partial-failure signal. Everything else is retained as degraded success so
    checkpoints, artifacts, and diagnostics remain available.
    """

    status = str(summary.get("status", "failed") or "failed").strip().lower()
    explicit_reason = str(summary.get("reason", "") or "").strip().lower()

    artifacts = _as_int(summary, "total_artifacts")
    ingest_ok = _as_int(summary, "ingest_ok")
    ingest_err = _as_int(summary, "ingest_err")
    failed_routes = _as_int(summary, "failed_routes")
    publish_attempts = _as_int(summary, "publish_attempts")
    publish_failures = _as_int(summary, "publish_failures")
    publish_pending = _as_int(summary, "publish_pending")
    publish_cancelled = _as_int(summary, "publish_cancelled")
    build_pending = _as_int(summary, "build_pending")
    build_cancelled = _as_int(summary, "build_cancelled")
    ingestion_cancelled = _as_int(summary, "ingestion_cancelled")
    lifo_pages = _as_int(summary, "lifo_pages_processed")
    lifo_windows_completed = _as_int(summary, "lifo_windows_completed")
    lifo_window_failures = _as_int(summary, "lifo_window_failures")
    export_failures = _as_int(summary, "export_failures")
    cleanup_failures = _as_int(summary, "cleanup_failures")

    recoverable_progress = any(
        (
            artifacts > 0,
            ingest_ok > 0,
            lifo_pages > 0,
            lifo_windows_completed > 0,
            bool(summary.get("state_preserved")),
            bool(summary.get("checkpoint_ready")),
        )
    )

    fatal_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if explicit_reason in _FATAL_REASONS:
        fatal_reasons.append(explicit_reason)

    if status == "completed":
        pass
    elif status == "partial":
        degraded_reasons.append("partial_run")
    elif status == "timed_out":
        if recoverable_progress or bool(summary.get("ingestion_budget_exhausted")):
            degraded_reasons.append("deadline_exhausted_after_recoverable_progress")
        else:
            fatal_reasons.append("deadline_exhausted_without_recoverable_progress")
    elif status == "failed":
        if fatal_reasons:
            pass
        elif recoverable_progress or ingest_err > 0 or failed_routes > 0 or publish_failures > 0:
            degraded_reasons.append("failed_stage_isolated_from_preserved_state")
        else:
            fatal_reasons.append("run_failed_without_recoverable_progress")
    else:
        if recoverable_progress:
            degraded_reasons.append(f"unknown_status:{status}")
        else:
            fatal_reasons.append(f"unknown_status_without_progress:{status}")

    if ingest_err:
        degraded_reasons.append("source_failures")
    if failed_routes:
        degraded_reasons.append("route_failures")
    if publish_failures:
        degraded_reasons.append("publish_failures")
    if publish_attempts > 0 and publish_failures >= publish_attempts and not no_publish:
        degraded_reasons.append("all_publish_attempts_failed")
    if publish_pending:
        degraded_reasons.append("publish_work_pending")
    if publish_cancelled:
        degraded_reasons.append("publish_work_cancelled")
    if build_pending:
        degraded_reasons.append("build_work_pending")
    if build_cancelled:
        degraded_reasons.append("build_work_cancelled")
    if ingestion_cancelled:
        degraded_reasons.append("ingestion_work_cancelled")
    if lifo_window_failures:
        degraded_reasons.append("lifo_window_failures")
    if export_failures:
        degraded_reasons.append("export_failures")
    if cleanup_failures:
        degraded_reasons.append("cleanup_failures")
    if bool(summary.get("ingestion_budget_exhausted")):
        degraded_reasons.append("ingestion_budget_exhausted")
    if artifacts == 0 and status != "failed":
        degraded_reasons.append("no_new_artifacts")

    if fatal_reasons:
        disposition = "fatal"
        reasons = _dedupe(fatal_reasons + degraded_reasons)
    elif degraded_reasons:
        disposition = "degraded"
        reasons = _dedupe(degraded_reasons)
    else:
        disposition = "success"
        reasons = ()

    metrics: dict[str, Any] = {
        "total_artifacts": artifacts,
        "ingest_ok": ingest_ok,
        "ingest_err": ingest_err,
        "failed_routes": failed_routes,
        "publish_attempts": publish_attempts,
        "publish_failures": publish_failures,
        "publish_pending": publish_pending,
        "publish_cancelled": publish_cancelled,
        "build_pending": build_pending,
        "build_cancelled": build_cancelled,
        "ingestion_cancelled": ingestion_cancelled,
        "lifo_pages_processed": lifo_pages,
        "lifo_windows_completed": lifo_windows_completed,
        "lifo_window_failures": lifo_window_failures,
        "export_failures": export_failures,
        "cleanup_failures": cleanup_failures,
        "ingestion_budget_exhausted": bool(summary.get("ingestion_budget_exhausted")),
        "timed_out_stage": summary.get("timed_out_stage"),
    }

    return RunHealth(
        disposition=disposition,
        status=status,
        reasons=reasons,
        recoverable_progress=recoverable_progress,
        metrics=metrics,
    )


def emit_run_health(
    summary: Mapping[str, Any],
    health: RunHealth,
    *,
    logger: logging.Logger,
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Log and optionally persist a machine-readable run-health envelope."""

    payload = {
        "schema_version": 1,
        **asdict(health),
        "summary": dict(summary),
    }
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    if health.disposition == "fatal":
        logger.error("HUNTX_RUN_HEALTH=%s", compact)
    elif health.disposition == "degraded":
        logger.warning("HUNTX_RUN_HEALTH=%s", compact)
    else:
        logger.info("HUNTX_RUN_HEALTH=%s", compact)

    target_raw = str(path or os.environ.get("HUNTX_RUN_SUMMARY_PATH", "")).strip()
    if target_raw:
        target = Path(target_raw)
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except Exception:
            logger.exception("Could not persist run-health report to %s", target)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    return payload
