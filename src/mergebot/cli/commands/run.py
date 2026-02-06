import logging
from pathlib import Path
from ...config.loader import load_config
from ...config.validate import validate_config
from ...core.orchestrator import Orchestrator
from ...core.locks import acquire_lock
from ...store.paths import STATE_DIR

def run_command(config_path: str):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        print(f"Config file not found: {cfg_path}")
        return

    config = load_config(cfg_path)
    validate_config(config)

    lock_path = STATE_DIR / "mergebot.lock"
    with acquire_lock(lock_path):
        orch = Orchestrator(config)
        orch.run()
