import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from ..config.loader import load_config
from ..config.validate import validate_config
from ..logging_conf import setup_logging
from ..store import paths

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="huntx CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--data-dir", default=os.getenv("HUNTX_DATA_DIR", "./data"), help="Data directory")
    parser.add_argument("--db-path", default=None, help="State DB path (overrides HUNTX_STATE_DB_PATH)")

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the huntx pipeline")
    run_parser.add_argument("--msg-fresh-hours", type=float, default=2)
    run_parser.add_argument("--file-fresh-hours", type=float, default=48)
    run_parser.add_argument("--msg-subsequent-hours", type=float, default=0)
    run_parser.add_argument("--file-subsequent-hours", type=float, default=0)
    run_parser.add_argument("--no-auto-deliver", action="store_true")
    run_parser.add_argument("--no-publish", action="store_true")

    bot_parser = subparsers.add_parser("bot", help="Run the interactive bot persistently")
    bot_parser.add_argument("--token", default=None)
    bot_parser.add_argument("--api-id", type=int, default=None)
    bot_parser.add_argument("--api-hash", default=None)

    clean_parser = subparsers.add_parser("clean", help="Delete all data")
    clean_parser.add_argument("--yes", "-y", action="store_true")

    reset_parser = subparsers.add_parser("reset", help="Full factory reset")
    reset_parser.add_argument("--yes", "-y", action="store_true")

    prune_parser = subparsers.add_parser("prune", help="Prune old data")
    prune_parser.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    db_path = args.db_path or os.getenv("HUNTX_STATE_DB_PATH") or str(Path(args.data_dir) / "state" / "state.db")
    paths.set_paths(args.data_dir, db_path)
    paths.ensure_dirs()

    log_dir = Path(args.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(
        log_level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        log_file=str(log_dir / "huntx.log"),
    )

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "bot":
        _cmd_bot(args)
    elif args.command == "clean":
        _cmd_clean(args)
    elif args.command == "reset":
        _cmd_reset(args)
    elif args.command == "prune":
        _cmd_prune(args)
