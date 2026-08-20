import logging
import os
from pathlib import Path

from ...logging_conf import setup_logging
from ...store import paths
from ..run_service import execute_pipeline_run


def run_command(config_path: str):
    """Compatibility run helper backed by the canonical governed runtime."""
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    paths.ensure_dirs()
    paths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = paths.LOGS_DIR / "huntx.log"
    setup_logging(log_level=log_level, log_file=str(log_file))
    logger = logging.getLogger(__name__)

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        logger.error("Config file not found: %s", cfg_path)
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    try:
        execution = execute_pipeline_run(
            cfg_path,
            no_publish=False,
            health_logger=logger,
        )
        health = execution.health
        if health.is_fatal:
            raise RuntimeError(
                "Health Gate FATAL: "
                f"status={health.status} reasons={list(health.reasons)} metrics={health.metrics}"
            )
        if health.disposition == "degraded":
            logger.warning(
                "Health Gate DEGRADED SUCCESS: reasons=%s metrics=%s",
                list(health.reasons),
                health.metrics,
            )
        else:
            logger.info("Health Gate SUCCESS: metrics=%s", health.metrics)
        return execution.summary
    except Exception as exc:
        logger.exception("Fatal error during run: %s", exc)
        raise
