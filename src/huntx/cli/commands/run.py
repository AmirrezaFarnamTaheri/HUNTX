import logging
import os
from pathlib import Path

from ...config.loader import load_config
from ...config.validate import validate_config
from ...core.locks import acquire_lock
from ...core.orchestrator import Orchestrator
from ...core.run_health import emit_run_health, evaluate_run_health
from ...logging_conf import setup_logging
from ...store import paths
from ...utils.env import env_bool, env_int


def run_command(config_path: str):
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

    max_workers = env_int("HUNTX_MAX_WORKERS", 3, min_value=1, max_value=64)
    timeout_raw = os.getenv("HUNTX_RUN_TIMEOUT", "12600")
    try:
        run_timeout = float(timeout_raw)
    except ValueError as exc:
        raise ValueError(f"HUNTX_RUN_TIMEOUT must be numeric, got {timeout_raw!r}") from exc
    if run_timeout <= 0:
        raise ValueError("HUNTX_RUN_TIMEOUT must be greater than zero")

    allow_partial_export = env_bool("HUNTX_ALLOW_PARTIAL_EXPORT", True)

    try:
        config = load_config(cfg_path)
        validate_config(config)

        lock_path = paths.STATE_DIR / "huntx.lock"
        with acquire_lock(lock_path):
            orch = Orchestrator(config, max_workers=max_workers)
            run_summary = orch.run(
                timeout=run_timeout,
                allow_partial_export=allow_partial_export,
            )

        health = evaluate_run_health(run_summary, no_publish=False)
        emit_run_health(run_summary, health, logger=logger)
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
    except Exception as exc:
        logger.exception("Fatal error during run: %s", exc)
        raise
