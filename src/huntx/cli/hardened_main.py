import logging
import os
from contextlib import nullcontext
from pathlib import Path

from . import main as legacy
from ..config.loader import load_config
from ..config.validate import validate_config
from ..core.hardened_orchestrator import HardenedOrchestrator
from ..core.locks import acquire_lock
from ..core.session_lease import session_lease_path
from ..store import paths

logger = logging.getLogger(__name__)


def _cmd_run(args):
    max_workers_raw = os.environ.get("HUNTX_MAX_WORKERS") or "3"
    try:
        max_workers = int(max_workers_raw)
    except ValueError:
        logger.warning("Invalid HUNTX_MAX_WORKERS=%r; using 3", max_workers_raw)
        max_workers = 3

    fetch_windows = {
        "msg_fresh_hours": args.msg_fresh_hours,
        "file_fresh_hours": args.file_fresh_hours,
        "msg_subsequent_hours": args.msg_subsequent_hours,
        "file_subsequent_hours": args.file_subsequent_hours,
    }
    allow_partial = os.environ.get("HUNTX_ALLOW_PARTIAL_SUCCESS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    allow_partial_export = os.environ.get("HUNTX_ALLOW_PARTIAL_EXPORT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    try:
        config = load_config(args.config)
        validate_config(config)
        timeout_raw = os.environ.get("HUNTX_RUN_TIMEOUT", "9000")
        try:
            run_timeout = float(timeout_raw)
        except ValueError:
            logger.warning("Invalid HUNTX_RUN_TIMEOUT=%r; using 9000", timeout_raw)
            run_timeout = 9000.0

        process_lock = Path(paths.STATE_DIR) / "huntx.lock"
        session_identity = os.environ.get("TELEGRAM_USER_SESSION", "").strip()
        session_lock = (
            acquire_lock(session_lease_path(Path(paths.STATE_DIR), session_identity))
            if session_identity
            else nullcontext()
        )
        with acquire_lock(process_lock), session_lock:
            orchestrator = HardenedOrchestrator(
                config,
                max_workers=max_workers,
                fetch_windows=fetch_windows,
            )
            summary = orchestrator.run(
                timeout=run_timeout,
                no_publish=args.no_publish,
                allow_partial_export=allow_partial_export,
            )

        status = summary.get("status", "failed")
        if status in {"failed", "timed_out"}:
            logger.error("Health Gate FAILED: run status=%s summary=%s", status, summary)
            raise SystemExit(1)
        if status == "partial" and not allow_partial:
            logger.error(
                "Health Gate FAILED: partial run requires HUNTX_ALLOW_PARTIAL_SUCCESS=true; summary=%s",
                summary,
            )
            raise SystemExit(1)
        if summary.get("total_artifacts", 0) == 0:
            logger.error("Health Gate FAILED: zero artifacts were built; summary=%s", summary)
            raise SystemExit(1)
        publish_attempts = int(summary.get("publish_attempts", 0))
        publish_failures = int(summary.get("publish_failures", 0))
        if not args.no_publish and publish_attempts > 0 and publish_failures >= publish_attempts:
            logger.error("Health Gate FAILED: all publish attempts failed; summary=%s", summary)
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception:
        logger.exception("Fatal pipeline error")
        raise SystemExit(1)

    if not args.no_auto_deliver:
        legacy._deliver_updates()


def main():
    legacy._cmd_run = _cmd_run  # type: ignore[assignment]
    legacy.main()


if __name__ == "__main__":
    main()