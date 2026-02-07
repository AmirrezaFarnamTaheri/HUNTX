import logging
import os
from pathlib import Path
from ...logging_conf import setup_logging
from ...config.loader import load_config
from ...config.validate import validate_config
from ...core.orchestrator import Orchestrator
from ...core.locks import acquire_lock
from ...store.paths import STATE_DIR

def run_command(config_path: str):
    # Setup logging
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    setup_logging(log_level=log_level)

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        logging.error(f"Config file not found: {cfg_path}")
        return

    try:
        config = load_config(cfg_path)
        validate_config(config)

        lock_path = STATE_DIR / "mergebot.lock"
        with acquire_lock(lock_path):
            orch = Orchestrator(config)
            orch.run()
    except Exception as e:
        logging.exception(f"Fatal error during run: {e}")
        raise
