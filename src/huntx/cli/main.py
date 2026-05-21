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
    run_parser.add_argument("--no-auto-deliver", action="store_true",
                            help="Skip automatic subscription delivery after pipeline")
    run_parser.add_argument("--no-publish", action="store_true",
                            help="Skip publishing artifacts to destination channels")

    # bot subcommand — persistent standalone bot
    bot_parser = subparsers.add_parser("bot", help="Run the interactive bot persistently")
    bot_parser.add_argument("--token", default=None, help="Bot token (default: PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN)")
    bot_parser.add_argument("--api-id", type=int, default=None, help="Telegram API ID")
    bot_parser.add_argument("--api-hash", default=None, help="Telegram API hash")

    # clean subcommand
    clean_parser = subparsers.add_parser("clean", help="Delete all data, state, cache for a fresh start")
    clean_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # reset subcommand — full factory reset
    reset_parser = subparsers.add_parser(
        "reset",
        help="Full factory reset: wipe ALL data, state, caches, outputs, and source offsets",
    )
    reset_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # prune subcommand — manual database and raw store pruning
    prune_parser = subparsers.add_parser(
        "prune",
        help="Manual database and raw store auto-pruning",
    )
    prune_parser.add_argument("--days", type=int, default=30, help="Purge items older than N days (default: 30)")

    args = parser.parse_args()

    paths.set_paths(args.data_dir, args.db_path)
    paths.ensure_dirs()

    log_dir = Path(args.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "huntx.log"

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logging(log_level=getattr(logging, log_level, logging.INFO), log_file=str(log_file))

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



def _cmd_run(args):
    from ..core.orchestrator import Orchestrator
    from ..core.locks import acquire_lock

    max_workers_str = os.environ.get("HUNTX_MAX_WORKERS") or "3"
    try:
        max_workers = int(max_workers_str)
    except ValueError:
        logger.warning(
            f"Invalid HUNTX_MAX_WORKERS value '{max_workers_str}', defaulting to 3."
        )
        max_workers = 3
    logger.info(f"Starting HuntX — config={args.config}, workers={max_workers}")

    fetch_windows = {
        "msg_fresh_hours": args.msg_fresh_hours,
        "file_fresh_hours": args.file_fresh_hours,
        "msg_subsequent_hours": args.msg_subsequent_hours,
        "file_subsequent_hours": args.file_subsequent_hours,
    }

    try:
        config = load_config(args.config)
        validate_config(config)
        lock_path = Path(paths.STATE_DIR) / "huntx.lock"
        with acquire_lock(lock_path):
            orchestrator = Orchestrator(config, max_workers=max_workers, fetch_windows=fetch_windows)
            # 4.5 hours time limit
            orchestrator.run(timeout=16200, no_publish=args.no_publish)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

    # Auto-deliver subscription updates to all subscribers
    if not args.no_auto_deliver:
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

    logger.info("Starting HuntX bot in persistent mode...")
    bot = InteractiveBot(token, api_id, api_hash)
    asyncio.run(bot.start())


def _cmd_clean(args):
    """Delete all data, state, cache for a fresh start."""
    data_dir = Path(paths.DATA_DIR)
    db_path = Path(paths.STATE_DB_PATH)

    items = [
        paths.RAW_STORE_DIR,
        paths.OUTPUT_DIR,
        paths.DEV_OUTPUT_DIR,
        paths.ARTIFACT_STORE_DIR,
        paths.REJECTS_DIR,
        paths.LOGS_DIR,
        db_path,
    ]
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
    This returns every source to first-seen state.
    Includes a backup of the state DB before deletion.
    """
    db_path = Path(paths.STATE_DB_PATH)

    # Collect everything to wipe
    items_to_remove = [
        paths.RAW_STORE_DIR,
        paths.ARTIFACT_STORE_DIR,
        paths.REJECTS_DIR,
        paths.LOGS_DIR,
        paths.STATE_DIR,
        paths.OUTPUT_DIR,
        paths.DEV_OUTPUT_DIR,
        db_path,
    ]

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

    # Backup DB if it exists
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.bak")
        try:
            shutil.copy2(db_path, backup_path)
            print(f"Backed up state DB to: {backup_path}")
        except Exception as e:
            print(f"Warning: Failed to backup state DB: {e}")

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

    # Re-ensure standard directories
    paths.ensure_dirs()
    
    # Add READMEs to outputs so git tracks them
    (paths.OUTPUT_DIR / "README.md").write_text(
        "# huntx Outputs\n\nAuto-generated build output. Do not edit manually.\n",
        encoding="utf-8",
    )
    (paths.DEV_OUTPUT_DIR / "README.md").write_text(
        "# Dev Outputs\n\nAuto-generated as an all-time cumulative set. Do not edit manually.\n",
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

    logger.info("Delivering subscription updates via HuntX bot...")
    bot = InteractiveBot(token, api_id, api_hash)

    # Manual loop management to gracefully cancel Telethon's internal tasks
    # (asyncio.run() would destroy them ungracefully, causing RuntimeError)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot.deliver_updates())
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as e:
            logger.debug(f"Failed to cancel pending tasks cleanly: {e}")
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.debug(f"Failed to shutdown async generators cleanly: {e}")
        loop.close()


def _cmd_prune(args):
    """Manual database and raw store auto-pruning."""
    from ..state.db import open_db
    from ..state.repo import StateRepo
    from ..store.raw_store import RawStore

    db = open_db(paths.STATE_DB_PATH)
    repo = StateRepo(db)
    raw_store = RawStore()

    logger.info(f"Starting manual pruning (older than {args.days} days)...")
    print(f"Purging state database records older than {args.days} days...")

    try:
        res = repo.prune_old_data(args.days)
    except Exception as e:
        logger.error(f"Pruning failed: {e}")
        sys.exit(1)

    records_pruned = res.get("records", 0)
    seen_files_pruned = res.get("seen_files", 0)
    published_artifacts_pruned = res.get("published_artifacts", 0)
    raw_hashes = res.get("raw_hashes", [])

    print(f"Database statistics:")
    print(f"  - Seen files pruned: {seen_files_pruned}")
    print(f"  - Records pruned: {records_pruned}")
    print(f"  - Published artifacts pruned: {published_artifacts_pruned}")

    raw_pruned = 0
    if raw_hashes:
        print(f"Pruning {len(raw_hashes)} raw store files from disk...")
        raw_pruned = raw_store.prune_by_hashes(raw_hashes)
        print(f"  - Raw store files deleted: {raw_pruned}")
    else:
        print("No raw store files to prune.")

    print("Pruning complete.")


if __name__ == "__main__":
    main()

