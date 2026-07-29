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
from ..core.runtime_resilience import apply_runtime_resilience
from ..core.session_lease import session_lease_path
from ..pipeline.governed_build import GovernedBuildPipeline
from ..state.consumer_reconciliation import reconcile_configured_bot_consumers
from ..store import paths

logger = logging.getLogger(__name__)

apply_runtime_resilience()


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


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
    """Apply CLI > environment > default precedence for runtime paths.

    The legacy parser historically gave both path options unconditional defaults,
    which overwrote environment configuration even when the caller did not pass
    either option. The public entry point injects only missing global options so
    argparse still validates explicit CLI syntax and explicit values always win.
    """

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
    if no_publish or bool(summary.get("ingestion_budget_exhausted")):
        return False
    attempts = int(summary.get("publish_attempts", 0))
    failures = int(summary.get("publish_failures", 0))
    return attempts > 0 and failures >= attempts


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
    allow_partial = _enabled("HUNTX_ALLOW_PARTIAL_SUCCESS")
    allow_partial_export = _enabled("HUNTX_ALLOW_PARTIAL_EXPORT")

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

        status = summary.get("status", "failed")
        budget_partial = bool(summary.get("ingestion_budget_exhausted"))
        if status in {"failed", "timed_out"}:
            logger.error("Health Gate FAILED: run status=%s summary=%s", status, summary)
            raise SystemExit(1)
        if status == "partial" and not allow_partial and not budget_partial:
            logger.error(
                "Health Gate FAILED: partial run requires HUNTX_ALLOW_PARTIAL_SUCCESS=true; summary=%s",
                summary,
            )
            raise SystemExit(1)
        if status == "partial" and budget_partial:
            logger.warning(
                "Health Gate accepted deadline-bounded partial run; completed work "
                "was built, exported, and persisted. External publication may be "
                "degraded: %s",
                summary,
            )

        source_failures = int(summary.get("ingest_err", 0))
        source_successes = int(summary.get("ingest_ok", 0))
        if status == "completed" and source_failures:
            logger.warning(
                "Health Gate accepted degraded source coverage: %s source failure(s), "
                "%s successful source(s), and all release routes completed",
                source_failures,
                source_successes,
            )

        if summary.get("total_artifacts", 0) == 0:
            if budget_partial:
                logger.warning(
                    "Deadline-bounded partial run produced no new artifacts; "
                    "preserving previously published outputs"
                )
            else:
                logger.error("Health Gate FAILED: zero artifacts were built; summary=%s", summary)
                raise SystemExit(1)
        if _all_publish_failures_are_fatal(summary, no_publish=args.no_publish):
            logger.error("Health Gate FAILED: all publish attempts failed; summary=%s", summary)
            raise SystemExit(1)
        publish_attempts = int(summary.get("publish_attempts", 0))
        publish_failures = int(summary.get("publish_failures", 0))
        if budget_partial and publish_attempts > 0 and publish_failures >= publish_attempts:
            logger.warning(
                "All Telegram publish attempts failed during an accepted deadline-bounded "
                "partial run; local outputs and durable state remain valid"
            )
    except SystemExit:
        raise
    except Exception:
        logger.exception("Fatal pipeline error")
        raise SystemExit(1)

    if not args.no_auto_deliver:
        legacy._deliver_updates()


def main():
    legacy._cmd_run = _cmd_run  # type: ignore[assignment]
    sys.argv = _inject_runtime_path_arguments(sys.argv)
    legacy.main()


if __name__ == "__main__":
    main()
