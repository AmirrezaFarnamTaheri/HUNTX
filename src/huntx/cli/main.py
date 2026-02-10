import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from ..config.loader import load_config
from ..logging_conf import setup_logging
from ..store.paths import set_paths, DATA_DIR, STATE_DB_PATH

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="huntx CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    parser.add_argument("--db-path", default="./data/state/state.db", help="State DB path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run the huntx pipeline")
    run_parser.add_argument("--msg-fresh-hours", type=float, default=2,
                            help="Text message lookback hours for first-seen source (default: 2)")
    run_parser.add_argument("--file-fresh-hours", type=float, default=48,
                            help="File/media lookback hours for first-seen source (default: 48)")
    run_parser.add_argument("--msg-subsequent-hours", type=float, default=0,
                            help="Text message lookback hours on subsequent runs (0=all new, default: 0)")
    run_parser.add_argument("--file-subsequent-hours", type=float, default=0,
                            help="File/media lookback hours on subsequent runs (0=all new, default: 0)")
    run_parser.add_argument("--no-deliver", action="store_true",
                            help="Skip automatic subscription delivery after pipeline")

    # bot subcommand — persistent standalone bot
    bot_parser = subparsers.add_parser("bot", help="Run the interactive bot persistently")
    bot_parser.add_argument("--token", default=None, help="Bot token (default: PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN)")
    bot_parser.add_argument("--api-id", type=int, default=None, help="Telegram API ID")
    bot_parser.add_argument("--api-hash", default=None, help="Telegram API hash")

    # clean subcommand
    clean_parser = subparsers.add_parser("clean", help="Delete all data, state, cache for a fresh start")
    clean_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # reset subcommand — full factory reset
    reset_parser = subparsers.add_parser("reset", help="Full factory reset: wipe ALL data, state, caches, outputs, and source offsets")
    reset_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    set_paths(args.data_dir, args.db_path)

    log_dir = Path(args.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "huntx.log"

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logging(log_level=getattr(logging, log_level), log_file=str(log_file))

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "bot":
        _cmd_bot(args)
    elif args.command == "clean":
        _cmd_clean(args)
    elif args.command == "reset":
        _cmd_reset(args)


def _cmd_run(args):
    from ..core.orchestrator import Orchestrator

    max_workers = int(os.environ.get("HUNTX_MAX_WORKERS", "2"))
    logger.info(f"Starting HuntX — config={args.config}, workers={max_workers}")

    fetch_windows = {
        "msg_fresh_hours": args.msg_fresh_hours,
        "file_fresh_hours": args.file_fresh_hours,
        "msg_subsequent_hours": args.msg_subsequent_hours,
        "file_subsequent_hours": args.file_subsequent_hours,
    }

    try:
        config = load_config(args.config)
        orchestrator = Orchestrator(config, max_workers=max_workers, fetch_windows=fetch_windows)
        orchestrator.run()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

    # Auto-deliver subscription updates to all subscribers
    if not args.no_deliver:
        _deliver_updates()


def _cmd_bot(args):
    """Run the interactive bot persistently."""
    import asyncio
    from ..bot.interactive import InteractiveBot

    token = args.token or os.environ.get("PUBLISH_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    api_id = args.api_id or int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = args.api_hash or os.environ.get("TELEGRAM_API_HASH", "")

    if not token:
        logger.error("No bot token. Set PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN or use --token.")
        sys.exit(1)
    if not api_id or not api_hash:
        logger.error("API ID and hash required. Set TELEGRAM_API_ID/TELEGRAM_API_HASH or use --api-id/--api-hash.")
        sys.exit(1)

    logger.info("Starting GatherX bot in persistent mode...")
    bot = InteractiveBot(token, api_id, api_hash)
    asyncio.run(bot.start())


def _cmd_clean(args):
    """Delete all data, state, cache for a fresh start."""
    data_dir = Path(DATA_DIR)
    db_path = Path(STATE_DB_PATH)

    dirs_to_clean = ["raw", "output", "archive", "dist", "rejects", "logs"]
    items = [data_dir / d for d in dirs_to_clean] + [db_path]
    existing = [p for p in items if p.exists()]

    if not existing:
        print("Nothing to clean.")
        return

    print("The following will be deleted:")
    for p in existing:
        print(f"  {p}")

    if not args.yes:
        confirm = input("\nProceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    for p in existing:
        if p.is_dir():
            shutil.rmtree(p)
            logger.info(f"Removed directory: {p}")
        elif p.is_file():
            p.unlink()
            logger.info(f"Removed file: {p}")

    print("Cleanup complete.")


def _cmd_reset(args):
    """Full factory reset: wipe ALL data, state, caches, outputs, and source offsets.
    This returns every source to first-seen state."""
    data_dir = Path(DATA_DIR)
    db_path = Path(STATE_DB_PATH)
    repo_root = Path.cwd()

    # Collect everything to wipe
    data_subdirs = ["raw", "output", "archive", "dist", "rejects", "logs", "artifacts", "state"]
    items_to_remove = [data_dir / d for d in data_subdirs]
    items_to_remove.append(db_path)

    # Repo-tracked output directories
    repo_outputs = [repo_root / "outputs", repo_root / "outputs_dev"]
    for d in repo_outputs:
        if d.exists():
            items_to_remove.append(d)

    existing = [p for p in items_to_remove if p.exists()]

    if not existing:
        print("Nothing to reset — already clean.")
        return

    print("=== FULL FACTORY RESET ===")
    print("This will DELETE all of the following and reset all sources to first-seen state:\n")
    for p in existing:
        label = "(dir)" if p.is_dir() else "(file)"
        print(f"  {label}  {p}")

    if not args.yes:
        confirm = input("\nType 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Aborted.")
            return

    removed = 0
    for p in existing:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
            removed += 1
            logger.info(f"[Reset] Removed: {p}")
        except Exception as e:
            logger.error(f"[Reset] Failed to remove {p}: {e}")

    # Recreate outputs dirs with READMEs so git tracks them
    outputs_dir = repo_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "README.md").write_text(
        "# huntx Outputs\n\nAuto-generated build output. Do not edit manually.\n",
        encoding="utf-8",
    )

    outputs_dev_dir = repo_root / "outputs_dev"
    outputs_dev_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dev_dir / "README.md").write_text(
        "# Dev Outputs\n\nAuto-generated with 48h rolling window. Do not edit manually.\n",
        encoding="utf-8",
    )

    print(f"\nReset complete. Removed {removed} item(s).")
    print("All sources will be treated as first-seen on the next run.")


def _deliver_updates():
    """Auto-deliver subscription updates to all subscribers after pipeline."""
    import asyncio
    from ..bot.interactive import InteractiveBot

    token = os.environ.get("PUBLISH_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")

    if not token or not api_id or not api_hash:
        logger.warning("Bot credentials not configured — skipping subscription delivery.")
        return

    logger.info("Delivering subscription updates via GatherX bot...")
    bot = InteractiveBot(token, api_id, api_hash)
    asyncio.run(bot.deliver_updates())


if __name__ == "__main__":
    main()
