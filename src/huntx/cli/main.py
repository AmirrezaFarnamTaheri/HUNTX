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

    run_parser = subparsers.add_parser("run", help="Run the huntx pipeline")
    run_parser.add_argument(
        "--msg-fresh-hours",
        type=float,
        default=2,
        help="Text message lookback hours for first-seen source (default: 2)",
    )
    run_parser.add_argument(
        "--file-fresh-hours",
        type=float,
        default=48,
        help="File/media lookback hours for first-seen source (default: 48)",
    )
    run_parser.add_argument(
        "--msg-subsequent-hours",
        type=float,
        default=0,
        help="Text message lookback hours on subsequent runs (0=all new, default: 0)",
    )
    run_parser.add_argument(
        "--file-subsequent-hours",
        type=float,
        default=0,
        help="File/media lookback hours on subsequent runs (0=all new, default: 0)",
    )
    run_parser.add_argument(
        "--no-auto-deliver",
        action="store_true",
        help="Skip automatic subscription delivery after pipeline",
    )
    run_parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Skip publishing artifacts to destination channels",
    )

    bot_parser = subparsers.add_parser("bot", help="Run the interactive bot persistently")
    bot_parser.add_argument(
        "--token",
        default=None,
        help="Bot token (default: PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN)",
    )
    bot_parser.add_argument("--api-id", type=int, default=None, help="Telegram API ID")
    bot_parser.add_argument("--api-hash", default=None, help="Telegram API hash")

    clean_parser = subparsers.add_parser(
        "clean", help="Delete all data, state, cache for a fresh start"
    )
    clean_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    reset_parser = subparsers.add_parser(
        "reset",
        help="Full factory reset: wipe ALL data, state, caches, outputs, and source offsets",
    )
    reset_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    prune_parser = subparsers.add_parser(
        "prune",
        help="Manual database and raw store auto-pruning",
    )
    prune_parser.add_argument(
        "--days", type=int, default=30, help="Purge items older than N days (default: 30)"
    )

    args = parser.parse_args()

    paths.set_paths(args.data_dir, args.db_path)
    paths.ensure_dirs()

    log_dir = Path(args.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "huntx.log"

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logging(
        log_level=getattr(logging, log_level, logging.INFO),
        log_file=str(log_file),
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


def _cmd_run(args):
    from ..core.locks import acquire_lock
    from ..core.orchestrator import Orchestrator

    max_workers_str = os.environ.get("HUNTX_MAX_WORKERS") or "3"
    try:
        max_workers = int(max_workers_str)
    except ValueError:
        logger.warning(
            "Invalid HUNTX_MAX_WORKERS value %r, defaulting to 3.",
            max_workers_str,
        )
        max_workers = 3
    logger.info("Starting HuntX — config=%s, workers=%s", args.config, max_workers)

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
            orchestrator = Orchestrator(
                config,
                max_workers=max_workers,
                fetch_windows=fetch_windows,
            )
            timeout_str = os.getenv("HUNTX_RUN_TIMEOUT", "9000")
            try:
                run_timeout = float(timeout_str)
            except ValueError:
                run_timeout = 9000.0
            run_summary = orchestrator.run(
                timeout=run_timeout,
                no_publish=args.no_publish,
            )

            status = run_summary.get("status", "failed")
            allow_partial = os.getenv("HUNTX_ALLOW_PARTIAL_SUCCESS", "").strip().lower()
            if status in {"failed", "timed_out"}:
                logger.error("Health Gate FAILED: run status=%s", status)
                sys.exit(1)
            if status == "partial" and allow_partial not in {"1", "true", "yes"}:
                logger.error(
                    "Health Gate FAILED: partial run requires HUNTX_ALLOW_PARTIAL_SUCCESS=true"
                )
                sys.exit(1)

            total_artifacts = run_summary.get("total_artifacts", 0)
            publish_attempts = run_summary.get("publish_attempts", 0)
            publish_failures = run_summary.get("publish_failures", 0)
            successful_publishes = publish_attempts - publish_failures

            if total_artifacts == 0:
                logger.error("Health Gate FAILED: Zero artifacts were built during this run.")
                sys.exit(1)
            if (
                not args.no_publish
                and publish_attempts > 0
                and successful_publishes == 0
            ):
                logger.error(
                    "Health Gate FAILED: Publishing was attempted but all publish tasks failed."
                )
                sys.exit(1)
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)

    if not args.no_auto_deliver:
        _deliver_updates()


def _cmd_bot(args):
    """Run the interactive bot persistently."""
    import asyncio

    from ..bot.interactive import InteractiveBot

    token = (
        args.token
        or os.environ.get("PUBLISH_BOT_TOKEN")
        or os.environ.get("TELEGRAM_TOKEN")
    )
    api_id = args.api_id or int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = args.api_hash or os.environ.get("TELEGRAM_API_HASH", "")

    if not token:
        logger.error(
            "No bot token. Set PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN or use --token."
        )
        sys.exit(1)

    ingest_token = os.environ.get("TELEGRAM_TOKEN")
    if ingest_token and token == ingest_token:
        logger.warning(
            "⚠️  WARNING (F-09): The persistent bot and the ingest pipeline are sharing "
            "the same TELEGRAM_TOKEN. If the pipeline runs while the bot is active, "
            "Telegram will return '409 Conflict' errors. Please use a distinct "
            "PUBLISH_BOT_TOKEN for the GatherX bot."
        )

    if not api_id or not api_hash:
        logger.error(
            "API ID and hash required. Set TELEGRAM_API_ID/TELEGRAM_API_HASH "
            "or use --api-id/--api-hash."
        )
        sys.exit(1)

    logger.info("Starting HuntX bot in persistent mode...")
    bot = InteractiveBot(token, api_id, api_hash)
    asyncio.run(bot.start())


def _backup_bot_users(db_path):
    import sqlite3

    if not Path(db_path).exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_users'"
        )
        if not cursor.fetchone():
            conn.close()
            return None
        rows = cursor.execute("SELECT * FROM bot_users").fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return data
    except Exception as exc:
        logger.warning("Failed to backup bot_users: %s", exc)
        return None


def _restore_bot_users(db_path, data):
    """Restore users through the canonical state schema and migrations.

    ``schema.sql`` + ``DBConnection._check_migrations`` are the single source of
    truth. Keeping another CREATE TABLE statement here previously allowed the
    reset path to drift from normal database initialization.
    """
    if not data:
        return

    from ..state.db import open_db

    try:
        db = open_db(Path(db_path))
        with db.connect() as conn:
            table_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(bot_users)").fetchall()
            }
            columns = [column for column in data[0].keys() if column in table_columns]
            required = {"user_id", "chat_id", "registered_at"}
            if not required.issubset(columns):
                missing = sorted(required - set(columns))
                raise RuntimeError(
                    f"Cannot restore bot_users backup; required columns missing: {missing}"
                )

            placeholders = ", ".join("?" for _ in columns)
            query = (
                f"INSERT OR REPLACE INTO bot_users ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            )
            for row in data:
                conn.execute(query, tuple(row.get(column) for column in columns))
        logger.info("Restored %s subscribers to bot_users table.", len(data))
    except Exception as exc:
        logger.error("Failed to restore bot_users: %s", exc)
        raise


def _cmd_clean(args):
    """Delete all data, state, cache for a fresh start."""
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
    existing = [path for path in items if path.exists()]

    if not existing:
        print("Nothing to clean.")
        return

    print("The following will be deleted:")
    for path in existing:
        print(f"  {path}")

    if not args.yes:
        confirm = input("\nProceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    bot_users_data = _backup_bot_users(db_path)

    for path in existing:
        if path.is_dir():
            shutil.rmtree(path)
            logger.info("Removed directory: %s", path)
        elif path.is_file():
            path.unlink()
            logger.info("Removed file: %s", path)

    paths.ensure_dirs()
    if bot_users_data:
        _restore_bot_users(db_path, bot_users_data)

    print("Cleanup complete.")


def _cmd_reset(args):
    """Full factory reset while preserving bot subscriber records."""
    db_path = Path(paths.STATE_DB_PATH)

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

    existing = [path for path in items_to_remove if path.exists()]

    if not existing:
        print("Nothing to reset — already clean.")
        return

    print("=== FULL FACTORY RESET ===")
    print(
        "This will DELETE all of the following and reset all sources "
        "to first-seen state:\n"
    )
    for path in existing:
        label = "(dir)" if path.is_dir() else "(file)"
        print(f"  {label}  {path}")

    if not args.yes:
        confirm = input("\nType 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Aborted.")
            return

    if db_path.exists():
        backup_path = db_path.with_suffix(".db.bak")
        try:
            shutil.copy2(db_path, backup_path)
            print(f"Backed up state DB to: {backup_path}")
        except Exception as exc:
            print(f"Warning: Failed to backup state DB: {exc}")

    bot_users_data = _backup_bot_users(db_path)

    removed = 0
    for path in existing:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            removed += 1
            logger.info("[Reset] Removed: %s", path)
        except Exception as exc:
            logger.error("[Reset] Failed to remove %s: %s", path, exc)

    paths.ensure_dirs()

    if bot_users_data:
        _restore_bot_users(db_path, bot_users_data)

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
        except Exception as exc:
            logger.debug("Failed to cancel pending tasks cleanly: %s", exc)
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as exc:
            logger.debug("Failed to shutdown async generators cleanly: %s", exc)
        loop.close()


def _cmd_prune(args):
    """Manual database and raw-store pruning with a post-delete live-reference guard."""
    from ..state.db import open_db
    from ..state.repo import StateRepo
    from ..store.raw_store import RawStore

    db = open_db(paths.STATE_DB_PATH)
    repo = StateRepo(db)
    raw_store = RawStore()

    logger.info("Starting manual pruning (older than %s days)...", args.days)
    print(f"Purging state database records older than {args.days} days...")

    try:
        result = repo.prune_old_data(args.days)
        candidate_hashes = set(result.get("raw_hashes", []))
        # A candidate hash can still be referenced by another, newer seen_files
        # row with identical content. Re-check after DB pruning before deleting
        # the content-addressed blob from disk.
        live_hashes = repo.get_all_known_hashes() if candidate_hashes else set()
        orphaned_hashes = sorted(candidate_hashes - live_hashes)
        skipped_live_hashes = candidate_hashes & live_hashes
    except Exception as exc:
        logger.error("Pruning failed: %s", exc)
        sys.exit(1)

    records_pruned = result.get("records", 0)
    seen_files_pruned = result.get("seen_files", 0)
    published_artifacts_pruned = result.get("published_artifacts", 0)

    print("Database statistics:")
    print(f"  - Seen files pruned: {seen_files_pruned}")
    print(f"  - Records pruned: {records_pruned}")
    print(f"  - Published artifacts pruned: {published_artifacts_pruned}")
    print(f"  - Raw hashes still referenced: {len(skipped_live_hashes)}")

    if orphaned_hashes:
        print(f"Pruning {len(orphaned_hashes)} unreferenced raw store files from disk...")
        raw_pruned = raw_store.prune_by_hashes(orphaned_hashes)
        print(f"  - Raw store files deleted: {raw_pruned}")
    else:
        print("No unreferenced raw store files to prune.")

    print("Pruning complete.")


if __name__ == "__main__":
    main()
