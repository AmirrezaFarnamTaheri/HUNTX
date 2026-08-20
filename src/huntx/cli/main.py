import argparse
import logging
import os
from pathlib import Path

from ..core.run_health import emit_run_health, evaluate_run_health
from ..logging_conf import setup_logging
from ..store import paths
from ..utils.env import env_int
from .commands.maintenance import (
    backup_bot_users as _backup_bot_users,
    clean_command as _cmd_clean,
    prune_command as _cmd_prune,
    reset_command as _cmd_reset,
    restore_bot_users as _restore_bot_users,
)
from .run_service import emit_unhandled_failure, execute_pipeline_run

__all__ = ["main", "_backup_bot_users", "_restore_bot_users"]

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
        "clean", help="Delete runtime data/state/cache for a fresh start"
    )
    clean_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    reset_parser = subparsers.add_parser(
        "reset",
        help="Factory reset runtime state, caches, outputs, and source offsets",
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


def _cmd_run(args):
    """Execute the canonical governed production pipeline from the CLI."""
    fetch_windows = {
        "msg_fresh_hours": args.msg_fresh_hours,
        "file_fresh_hours": args.file_fresh_hours,
        "msg_subsequent_hours": args.msg_subsequent_hours,
        "file_subsequent_hours": args.file_subsequent_hours,
    }
    execution = None
    try:
        execution = execute_pipeline_run(
            args.config,
            fetch_windows=fetch_windows,
            no_publish=args.no_publish,
            health_logger=logger,
        )
        health = execution.health
        if health.is_fatal:
            logger.error(
                "Health Gate FATAL: status=%s reasons=%s metrics=%s",
                health.status,
                list(health.reasons),
                health.metrics,
            )
            raise SystemExit(1)
        if health.disposition == "degraded":
            logger.warning(
                "Health Gate DEGRADED SUCCESS: preserved useful work; reasons=%s metrics=%s",
                list(health.reasons),
                health.metrics,
            )
        else:
            logger.info("Health Gate SUCCESS: metrics=%s", health.metrics)
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("Fatal pipeline error")
        emit_unhandled_failure(exc, no_publish=args.no_publish, health_logger=logger)
        raise SystemExit(1) from exc

    if not args.no_auto_deliver:
        try:
            _deliver_updates()
        except (Exception, SystemExit):
            logger.exception("Post-run auto-delivery failed; durable run output is preserved")
            if execution is not None:
                execution.summary["post_run_delivery_failures"] = int(
                    execution.summary.get("post_run_delivery_failures", 0)
                ) + 1
                delivery_health = evaluate_run_health(
                    execution.summary,
                    no_publish=args.no_publish,
                )
                emit_run_health(execution.summary, delivery_health, logger=logger)


def _cmd_bot(args):
    """Run the interactive bot persistently."""
    import asyncio

    from ..bot.interactive import InteractiveBot

    token = args.token or os.environ.get("PUBLISH_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    api_id = args.api_id if args.api_id is not None else env_int("TELEGRAM_API_ID", 0, min_value=1)
    api_hash = args.api_hash or os.environ.get("TELEGRAM_API_HASH", "")

    if not token:
        logger.error("No bot token. Set PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN or use --token.")
        raise SystemExit(1)

    ingest_token = os.environ.get("TELEGRAM_TOKEN")
    if ingest_token and token == ingest_token:
        logger.warning(
            "The persistent bot and ingest pipeline share TELEGRAM_TOKEN; use a distinct "
            "PUBLISH_BOT_TOKEN to avoid Telegram getUpdates conflicts."
        )

    if not api_id or api_id < 1 or not api_hash:
        logger.error(
            "API ID and hash required. Set TELEGRAM_API_ID/TELEGRAM_API_HASH "
            "or use --api-id/--api-hash."
        )
        raise SystemExit(1)

    logger.info("Starting HuntX bot in persistent mode...")
    asyncio.run(InteractiveBot(token, api_id, api_hash).start())


def _deliver_updates():
    """Auto-deliver subscription updates to approved subscribers after a run."""
    import asyncio

    from ..bot.interactive import InteractiveBot

    token = os.environ.get("PUBLISH_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    api_id = env_int("TELEGRAM_API_ID", 0, min_value=1)
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")

    if not token or not api_id or not api_hash:
        logger.warning("Bot credentials not configured — skipping subscription delivery.")
        return

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


if __name__ == "__main__":
    main()
