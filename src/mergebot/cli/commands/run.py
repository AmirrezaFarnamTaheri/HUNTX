import logging
import os
from pathlib import Path
from ...logging_conf import setup_logging
from ...config.loader import load_config
from ...config.validate import validate_config
from ...core.orchestrator import Orchestrator
from ...core.locks import acquire_lock
from ...store.paths import STATE_DIR, LOGS_DIR


def run_command(config_path: str):
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "mergebot.log"
    setup_logging(log_level=log_level, log_file=str(log_file))

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        logging.error(f"Config file not found: {cfg_path}")
        return

    max_workers = int(os.getenv("MERGEBOT_MAX_WORKERS", "10"))

    try:
        config = load_config(cfg_path)
        validate_config(config)

        lock_path = STATE_DIR / "mergebot.lock"
        with acquire_lock(lock_path):
            orch = Orchestrator(config, max_workers=max_workers)
            orch.run()
    except Exception as e:
        logging.exception(f"Fatal error during run: {e}")
        raise
