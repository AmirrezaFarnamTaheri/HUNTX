import logging
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Sequence

from . import main as legacy
from ..config.loader import load_config
from ..config.validate import validate_config
from ..core.locks import acquire_lock
from ..core.optimized_orchestrator import OptimizedHardenedOrchestrator
from ..core.run_health import emit_run_health, evaluate_run_health
from ..core.runtime_resilience import apply_runtime_resilience
from ..core.session_lease import session_lease_path
from ..pipeline.governed_build import GovernedBuildPipeline
from ..state.consumer_reconciliation import reconcile_configured_bot_consumers
from ..store import paths

logger = logging.getLogger(__name__)

apply_runtime_resilience()


def _enabled(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _option_value(argv: Sequence[str], option: str) -> str | None:
    for index, value in enumerate(argv[1:], start=1):
        if value == option:
            if index + 1 < len(argv):
                return argv[index + 1]
            return None
        prefix = option + "="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return None


def _has_option(argv: Sequence[str], option: str) -> bool:
    return any(value == option or value.startswith(option + "=") for value in argv[1:])


def _inject_runtime_path_arguments(argv: Sequence[str]) -> list[str]:
    """Apply CLI > environment > default precedence for runtime paths."""

    resolved = list(argv)
    explicit_data = _option_value(resolved, "--data-dir")
    data_dir = explicit_data or os.environ.get("HUNTX_DATA_DIR") or "data"

    additions: list[str] = []
    if not _has_option(resolved, "--data-dir"):
        additions.extend(["--data-dir", data_dir])
    if not _has_option(resolved, "--db-path"):
        db_path = os.environ.get("HUNTX_STATE_DB_PATH") or str(Path(data_dir) / "state" / "state.db")
        additions.extend(["--db-path", db_path])
    return [resolved[0], *additions, *resolved[1:]]


def _all_publish_failures_are_fatal(
    summary: dict[str, Any],
    *,
    no_publish: bool,
) -> bool:
    """Compatibility shim: publication is best-effort, never a health-gate fatality.

    Failed delivery remains visible in the structured run-health report and
    durable publication state. It must not discard valid artifacts or prevent a
    checkpoint from advancing.
    """

    del summary, no_publish
    return False


def _cmd_run(args):
    max_workers_raw = os.environ.get("HUNTX_MAX_WORKERS") or "3"
    try:
        max_workers = max(1, int(max_workers_raw))
    except ValueError:
        logger.warning("Invalid HUNTX_MAX_WORKERS=%r; using 3", max_workers_raw)
        max_workers = 3

    fetch_windows = {
        "msg_fresh_hours": args.msg_fresh_hours,
        "file_fresh_hours": args.file_fresh_hours,
        "msg_subsequent_hours": args.msg_subsequent_hours,
        "file_subsequent_hours": args.file_subsequent_hours,
    }
    allow_partial_export = _enabled("HUNTX_ALLOW_PARTIAL_EXPORT", default=True)

    summary: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        validate_config(config)
        timeout_raw = os.environ.get("HUNTX_RUN_TIMEOUT", "12600")
        try:
            run_timeout = float(timeout_raw)
        except ValueError:
            logger.warning("Invalid HUNTX_RUN_TIMEOUT=%r; using 12600", timeout_raw)
            run_timeout = 12600.0

        process_lock = Path(paths.STATE_DIR) / "huntx.lock"
        session_identity = os.environ.get("TELEGRAM_USER_SESSION", "").strip()
        session_lock = (
            acquire_lock(session_lease_path(Path(paths.STATE_DIR), session_identity))
            if session_identity
            else nullcontext()
        )
        with acquire_lock(process_lock), session_lock:
            orchestrator = OptimizedHardenedOrchestrator(
                config,
                max_workers=max_workers,
                fetch_windows=fetch_windows,
            )
            reconciliation = reconcile_configured_bot_consumers(orchestrator.repo, config)
            logger.info("Telegram consumer reconciliation: %s", reconciliation)
            route_policies = {
                route.name: (
                    route.publication_tier.value,
                    route.effective_require_fresh_probe,
                )
                for route in config.routes
            }
            orchestrator.build_pipeline = GovernedBuildPipeline(
                orchestrator.repo,
                orchestrator.artifact_store,
                orchestrator.registry,
                route_policies,
            )
            summary = orchestrator.run(
                timeout=run_timeout,
                no_publish=args.no_publish,
                allow_partial_export=allow_partial_export,
            )

        health = evaluate_run_health(summary, no_publish=args.no_publish)
        emit_run_health(summary, health, logger=logger)
        if health.is_fatal:
            logger.error(
                "Health Gate FATAL: status=%s reasons=%s metrics=%s",
                health.status,
                list(health.reasons),
                health.metrics,
            )
            raise SystemExit(1)
        if health.disposition == "degraded":
            logger.warning(
                "Health Gate DEGRADED SUCCESS: preserved useful work; reasons=%s metrics=%s",
                list(health.reasons),
                health.metrics,
            )
        else:
            logger.info("Health Gate SUCCESS: metrics=%s", health.metrics)
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("Fatal pipeline error")
        failure_summary = {
            "status": "failed",
            "reason": "unhandled_exception",
            "exception_type": type(exc).__name__,
            "total_artifacts": 0,
            "ingest_ok": 0,
            "ingest_err": 0,
        }
        failure_health = evaluate_run_health(failure_summary, no_publish=args.no_publish)
        emit_run_health(failure_summary, failure_health, logger=logger)
        raise SystemExit(1)

    if not args.no_auto_deliver:
        try:
            legacy._deliver_updates()
        except (Exception, SystemExit):
            logger.exception("Post-run auto-delivery failed; durable run output is preserved")
            if summary is not None:
                summary["post_run_delivery_failures"] = int(summary.get("post_run_delivery_failures", 0)) + 1
                delivery_health = evaluate_run_health(summary, no_publish=args.no_publish)
                emit_run_health(summary, delivery_health, logger=logger)


def main():
    legacy._cmd_run = _cmd_run  # type: ignore[assignment]
    sys.argv = _inject_runtime_path_arguments(sys.argv)
    legacy.main()


if __name__ == "__main__":
    main()
