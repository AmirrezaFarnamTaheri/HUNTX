import argparse
import logging
import os
import sys
from pathlib import Path

from ..config.loader import load_config
from ..logging_conf import setup_logging
from ..store.paths import set_paths

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="MergeBot CLI")

    # Global args
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    parser.add_argument("--db-path", default="./data/state/state.db", help="State DB path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the mergebot pipeline")

    args = parser.parse_args()

    # Set paths env vars before anything else
    set_paths(args.data_dir, args.db_path)

    # Setup logging
    # Ensure log dir exists
    log_dir = Path(args.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mergebot.log"

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logging(log_level=getattr(logging, log_level), log_file=str(log_file))

    if args.command == "run":
        # Delayed import to ensure paths are set
        from ..core.orchestrator import Orchestrator

        logger.info(f"Starting MergeBot with config: {args.config}")
        try:
            config = load_config(args.config)
            orchestrator = Orchestrator(config)
            orchestrator.run()
        except Exception as e:
            logger.exception(f"Fatal error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
