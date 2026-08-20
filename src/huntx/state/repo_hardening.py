from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable, Dict, Optional, Type


def _validate_fingerprint(token_fingerprint: str) -> None:
    if len(token_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in token_fingerprint
    ):
        raise ValueError("token_fingerprint must be a lowercase SHA-256 digest")


def _normalize_consumer_id(consumer_id: str) -> str:
    normalized = str(consumer_id).strip()
    if not normalized:
        raise ValueError("consumer_id is required")
    if len(normalized) > 512:
        raise ValueError("consumer_id is too long")
    return normalized


def _validate_retention_days(days: Any) -> int:
    """Require an explicit positive integer before any destructive pruning."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("retention days must be a positive integer")
    return days


def _record_file_atomic(
    self: Any,
    source_id: str,
    external_id: str,
    raw_hash: str,
    file_size: int,
    filename: str,
    status: str = "pending",
    metadata: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Atomically create or refresh one source observation."""

    metadata_json = json.dumps(metadata or {})
    normalized_external_id = str(external_id)

    def record(connection: sqlite3.Connection) -> int:
        connection.execute(
            """
            INSERT INTO seen_files
                (source_id, external_id, raw_hash, file_size, filename,
                 status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, external_id) DO NOTHING
            """,
            (
                source_id,
                normalized_external_id,
                raw_hash,
                file_size,
                filename,
                status,
                metadata_json,
            ),
        )
        existing = connection.execute(
            """
            SELECT id, raw_hash
            FROM seen_files
            WHERE source_id = ? AND external_id = ?
            """,
            (source_id, normalized_external_id),
        ).fetchone()
        if existing is None:
            raise RuntimeError("Failed to create or locate source observation")

        observation_id = int(existing["id"])
        if str(existing["raw_hash"]) != raw_hash:
            connection.execute(
                """
                UPDATE records
                SET is_active = 0
                WHERE source_observation_id = ? AND is_active = 1
                """,
                (observation_id,),
            )
            updated = connection.execute(
                """
                UPDATE seen_files
                SET raw_hash = ?, file_size = ?, filename = ?,
                    status = ?, error_msg = NULL, metadata_json = ?,
                    ingested_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    raw_hash,
                    file_size,
                    filename,
                    status,
                    metadata_json,
                    observation_id,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source observation refresh lost its target row")
        return observation_id

    if conn is not None:
        return record(conn)
    with self.db.connect() as owned_connection:
        return record(owned_connection)


def _register_bot_consumer(
    self: Any,
    token_fingerprint: str,
    consumer_id: str,
    acknowledged_update_id: int = 0,
) -> None:
    _validate_fingerprint(token_fingerprint)
    normalized_consumer = _normalize_consumer_id(consumer_id)
    watermark = max(0, int(acknowledged_update_id))
    now = time.time()
    with self.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO telegram_bot_consumers
                (token_fingerprint, consumer_id, acknowledged_update_id,
                 active, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(token_fingerprint, consumer_id) DO UPDATE SET
                acknowledged_update_id = MAX(
                    telegram_bot_consumers.acknowledged_update_id,
                    excluded.acknowledged_update_id
                ),
                active = 1,
                updated_at = excluded.updated_at
            """,
            (token_fingerprint, normalized_consumer, watermark, now),
        )


def _acknowledge_bot_consumer(
    self: Any,
    token_fingerprint: str,
    consumer_id: str,
    acknowledged_update_id: int,
    *,
    retain_last: int = 100,
) -> int:
    """Advance one consumer and prune below every active consumer."""

    _validate_fingerprint(token_fingerprint)
    normalized_consumer = _normalize_consumer_id(consumer_id)
    watermark = max(0, int(acknowledged_update_id))
    safety_window = max(0, int(retain_last))
    now = time.time()

    with self.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO telegram_bot_consumers
                (token_fingerprint, consumer_id, acknowledged_update_id,
                 active, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(token_fingerprint, consumer_id) DO UPDATE SET
                acknowledged_update_id = MAX(
                    telegram_bot_consumers.acknowledged_update_id,
                    excluded.acknowledged_update_id
                ),
                active = 1,
                updated_at = excluded.updated_at
            """,
            (token_fingerprint, normalized_consumer, watermark, now),
        )
        row = conn.execute(
            """
            SELECT MIN(acknowledged_update_id) AS safe_watermark
            FROM telegram_bot_consumers
            WHERE token_fingerprint = ? AND active = 1
            """,
            (token_fingerprint,),
        ).fetchone()
        safe_watermark = int(row["safe_watermark"] or 0) if row else 0
        prune_through = max(0, safe_watermark - safety_window)
        if prune_through <= 0:
            return 0
        deleted = conn.execute(
            """
            DELETE FROM telegram_bot_updates
            WHERE token_fingerprint = ? AND update_id <= ?
            """,
            (token_fingerprint, prune_through),
        )
        return max(0, int(deleted.rowcount))


def _deactivate_bot_consumer(
    self: Any,
    token_fingerprint: str,
    consumer_id: str,
) -> None:
    _validate_fingerprint(token_fingerprint)
    normalized_consumer = _normalize_consumer_id(consumer_id)
    with self.db.connect() as conn:
        conn.execute(
            """
            UPDATE telegram_bot_consumers
            SET active = 0, updated_at = ?
            WHERE token_fingerprint = ? AND consumer_id = ?
            """,
            (time.time(), token_fingerprint, normalized_consumer),
        )


def _get_bot_consumer_watermark(
    self: Any,
    token_fingerprint: str,
    consumer_id: str,
) -> int:
    _validate_fingerprint(token_fingerprint)
    normalized_consumer = _normalize_consumer_id(consumer_id)
    with self.db.connect() as conn:
        row = conn.execute(
            """
            SELECT acknowledged_update_id
            FROM telegram_bot_consumers
            WHERE token_fingerprint = ? AND consumer_id = ? AND active = 1
            """,
            (token_fingerprint, normalized_consumer),
        ).fetchone()
    return int(row["acknowledged_update_id"]) if row else 0


def _guarded_prune_factory(
    original: Callable[..., Dict[str, Any]],
) -> Callable[..., Dict[str, Any]]:
    def guarded(self: Any, days: int) -> Dict[str, Any]:
        return original(self, _validate_retention_days(days))

    guarded.__name__ = "prune_old_data"
    guarded.__doc__ = (
        "Purge state older than a positive integer retention window. "
        "Zero/negative/non-integer values are rejected before any SQL executes."
    )
    return guarded


def install_state_repo_hardening(state_repo_type: Type[Any]) -> None:
    """Install compatibility-preserving hardened StateRepo operations once."""
    if getattr(state_repo_type, "_state_repo_hardening_applied", False):
        return

    original_prune = state_repo_type.prune_old_data
    state_repo_type.record_file = _record_file_atomic
    state_repo_type.register_bot_consumer = _register_bot_consumer
    state_repo_type.acknowledge_bot_consumer = _acknowledge_bot_consumer
    state_repo_type.deactivate_bot_consumer = _deactivate_bot_consumer
    state_repo_type.get_bot_consumer_watermark = _get_bot_consumer_watermark
    state_repo_type.prune_old_data = _guarded_prune_factory(original_prune)
    state_repo_type._state_repo_hardening_applied = True
