from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from ...state.db import open_db
from ...state.repo import StateRepo
from ...store import paths
from ...store.raw_store import RawStore

logger = logging.getLogger(__name__)


def backup_bot_users(db_path: str | Path) -> list[dict[str, Any]] | None:
    """Read GatherX registrations or fail before destructive maintenance."""
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_users'"
            )
            if not cursor.fetchone():
                return None
            return [dict(row) for row in cursor.execute("SELECT * FROM bot_users").fetchall()]
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeError(
            "Could not preserve GatherX registrations; maintenance aborted"
        ) from exc


def restore_bot_users(db_path: str | Path, data: list[dict[str, Any]] | None) -> None:
    """Restore users through the canonical schema/migration path."""
    if not data:
        return

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
            update_columns = [column for column in columns if column != "user_id"]
            assignments = ", ".join(
                f"{column} = excluded.{column}" for column in update_columns
            )
            query = (
                f"INSERT INTO bot_users ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(user_id) DO UPDATE SET {assignments}"
            )
            for row in data:
                conn.execute(query, tuple(row.get(column) for column in columns))
        logger.info("Restored %s subscribers to bot_users table.", len(data))
    except Exception as exc:
        logger.error("Failed to restore bot_users: %s", exc)
        raise


def cleanup_targets(db_path: Path) -> list[Path]:
    """Return all runtime storage surfaces owned by clean/reset."""
    candidates = [
        paths.RAW_STORE_DIR,
        paths.ARTIFACT_STORE_DIR,  # legacy location retained for cleanup
        Path(paths.DATA_DIR) / "dist",
        Path(paths.DATA_DIR) / "archive",
        paths.REJECTS_DIR,
        paths.LOGS_DIR,
        paths.OUTPUT_DIR,
        paths.DEV_OUTPUT_DIR,
        db_path,
        paths.STATE_DIR,
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = Path(candidate).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(Path(candidate))
    return unique


def _remove_targets(existing: list[Path]) -> tuple[int, list[str]]:
    """Best-effort remove owned paths while preserving complete failure evidence."""
    removed = 0
    failures: list[str] = []
    for path in existing:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            else:
                continue
            removed += 1
            logger.info("Removed runtime path: %s", path)
        except Exception as exc:
            logger.error("Failed to remove %s: %s", path, exc)
            failures.append(f"{path}: {type(exc).__name__}")
    return removed, failures


def _raise_if_incomplete(action: str, failures: list[str]) -> None:
    if failures:
        raise RuntimeError(
            f"{action} incomplete; {len(failures)} runtime path(s) could not be removed: "
            + "; ".join(failures)
        )


def clean_command(args: Any) -> None:
    """Delete runtime data/state/cache while preserving registered bot users."""
    db_path = Path(paths.STATE_DB_PATH)
    existing = [path for path in cleanup_targets(db_path) if path.exists()]
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

    bot_users_data = backup_bot_users(db_path)
    _removed, failures = _remove_targets(existing)

    # Restore registrations before surfacing a partial deletion failure. This
    # avoids losing the preserved user set merely because a later owned path
    # could not be removed.
    paths.ensure_dirs()
    restore_bot_users(db_path, bot_users_data)
    _raise_if_incomplete("Cleanup", failures)
    print("Cleanup complete.")


def reset_command(args: Any) -> None:
    """Factory-reset runtime state while preserving GatherX registrations."""
    db_path = Path(paths.STATE_DB_PATH)
    existing = [path for path in cleanup_targets(db_path) if path.exists()]
    if not existing:
        print("Nothing to reset — already clean.")
        return

    print("=== FULL FACTORY RESET ===")
    print("This deletes runtime state and resets all sources to first-seen state:\n")
    for path in existing:
        label = "(dir)" if path.is_dir() else "(file)"
        print(f"  {label}  {path}")

    if not args.yes:
        confirm = input("\nType 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Aborted.")
            return

    if db_path.exists():
        backup_path = Path(paths.DATA_DIR) / "state.db.bak"
        try:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, backup_path)
        except OSError as exc:
            raise RuntimeError(
                f"Could not create reset backup at {backup_path}; reset aborted"
            ) from exc
        print(f"Backed up state DB to: {backup_path}")

    bot_users_data = backup_bot_users(db_path)
    removed, failures = _remove_targets(existing)

    paths.ensure_dirs()
    restore_bot_users(db_path, bot_users_data)

    (paths.OUTPUT_DIR / "README.md").write_text(
        "# huntx Outputs\n\nAuto-generated build output. Do not edit manually.\n",
        encoding="utf-8",
    )
    (paths.DEV_OUTPUT_DIR / "README.md").write_text(
        "# Dev Outputs\n\nAuto-generated as an all-time cumulative set. Do not edit manually.\n",
        encoding="utf-8",
    )

    _raise_if_incomplete("Reset", failures)
    print(f"\nReset complete. Removed {removed} item(s).")
    print("All sources will be treated as first-seen on the next run.")


def prune_command(args: Any) -> None:
    """Prune old DB state and only unreferenced raw blobs."""
    db = open_db(paths.STATE_DB_PATH)
    repo = StateRepo(db)
    raw_store = RawStore()

    logger.info("Starting manual pruning (older than %s days)...", args.days)
    print(f"Purging state database records older than {args.days} days...")

    try:
        result = repo.prune_old_data(args.days)
        candidate_hashes = set(result.get("raw_hashes", []))
        live_hashes = repo.get_all_known_hashes() if candidate_hashes else set()
        orphaned_hashes = sorted(candidate_hashes - live_hashes)
        skipped_live_hashes = candidate_hashes & live_hashes
    except Exception as exc:
        logger.error("Pruning failed: %s", exc)
        raise SystemExit(1) from exc

    print("Database statistics:")
    print(f"  - Seen files pruned: {result.get('seen_files', 0)}")
    print(f"  - Records pruned: {result.get('records', 0)}")
    print(f"  - Published artifacts pruned: {result.get('published_artifacts', 0)}")
    print(f"  - Raw hashes still referenced: {len(skipped_live_hashes)}")

    if orphaned_hashes:
        print(f"Pruning {len(orphaned_hashes)} unreferenced raw store files from disk...")
        raw_pruned = raw_store.prune_by_hashes(orphaned_hashes)
        print(f"  - Raw store files deleted: {raw_pruned}")
    else:
        print("No unreferenced raw store files to prune.")

    print("Pruning complete.")
