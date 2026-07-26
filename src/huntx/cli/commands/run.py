import logging
import os
from pathlib import Path
from ...logging_conf import setup_logging
from ...config.loader import load_config
from ...config.validate import validate_config
from ...core.orchestrator import Orchestrator
from ...core.locks import acquire_lock
from ...store import paths
from ...utils.env import env_int


def run_command(config_path: str):
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    paths.ensure_dirs()
    paths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = paths.LOGS_DIR / "huntx.log"
    setup_logging(log_level=log_level, log_file=str(log_file))

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        # Raise rather than return: a bare `return` exits 0, so a scheduler or
        # CI job treats a misconfigured run as a success. Every other failure
        # path in this function raises, so returning here was also inconsistent.
        logging.error(f"Config file not found: {cfg_path}")
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    max_workers = env_int("HUNTX_MAX_WORKERS", 3, min_value=1, max_value=64)

    try:
        config = load_config(cfg_path)
        validate_config(config)

        lock_path = paths.STATE_DIR / "huntx.lock"
        with acquire_lock(lock_path):
            orch = Orchestrator(config, max_workers=max_workers)
            run_summary = orch.run()

            total_artifacts = run_summary.get("total_artifacts", 0)
            publish_attempts = run_summary.get("publish_attempts", 0)
            publish_failures = run_summary.get("publish_failures", 0)
            successful_publishes = publish_attempts - publish_failures

            if total_artifacts == 0:
                raise RuntimeError("Health Gate FAILED: Zero artifacts were built during this run.")
            elif publish_attempts > 0 and successful_publishes == 0:
                raise RuntimeError("Health Gate FAILED: Publishing was attempted but all publish tasks failed.")
    except Exception as e:
        logging.exception(f"Fatal error during run: {e}")
        raise
