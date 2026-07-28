from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Mapping, Optional, Set, Type


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
    """Atomically create or refresh one source observation.

    The first statement is a write, so SQLite acquires its writer reservation
    before the row is inspected. Concurrent callers can no longer both observe
    a missing row and race into the UNIQUE(source_id, external_id) constraint.
    """

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
    """Advance one consumer and prune only below every active consumer.

    A bot token may feed several configured chats. Deleting through one chat's
    offset would lose updates for slower chats, so pruning is fenced by the
    minimum durable watermark across all active consumers for the token.
    """

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


def _normalize_desired_consumers(
    desired_consumers: Mapping[str, Set[str]],
) -> Dict[str, Set[str]]:
    normalized: Dict[str, Set[str]] = {}
    for token_fingerprint, consumers in desired_consumers.items():
        fingerprint = str(token_fingerprint)
        _validate_fingerprint(fingerprint)
        if isinstance(consumers, (str, bytes)):
            raise ValueError("consumer collection must be a set-like collection")
        normalized[fingerprint] = {
            _normalize_consumer_id(consumer_id) for consumer_id in consumers
        }
    return normalized


def _reconcile_bot_consumers(
    self: Any,
    desired_consumers: Mapping[str, Set[str]],
) -> Dict[str, int]:
    """Reconcile persisted Bot API consumer ownership with current config.

    This operation is deliberately transactional. Desired consumers are
    reactivated without resetting their durable watermarks, removed consumers
    are deactivated, and inbox rows are deleted only for tokens that are absent
    from the desired configuration and have no active consumer after the same
    transaction. Inactive consumer rows remain as durable history so a later
    re-addition resumes from its prior watermark rather than replaying from zero.
    """

    desired = _normalize_desired_consumers(desired_consumers)
    desired_pairs = {
        (fingerprint, consumer_id)
        for fingerprint, consumers in desired.items()
        for consumer_id in consumers
    }
    now = time.time()
    activated = 0
    deactivated = 0
    deleted_updates = 0

    with self.db.connect() as conn:
        existing_rows = conn.execute(
            """
            SELECT token_fingerprint, consumer_id, active
            FROM telegram_bot_consumers
            """
        ).fetchall()
        existing = {
            (str(row["token_fingerprint"]), str(row["consumer_id"])): int(row["active"])
            for row in existing_rows
        }

        for fingerprint, consumer_id in sorted(desired_pairs):
            prior_active = existing.get((fingerprint, consumer_id))
            conn.execute(
                """
                INSERT INTO telegram_bot_consumers
                    (token_fingerprint, consumer_id, acknowledged_update_id,
                     active, updated_at)
                VALUES (?, ?, 0, 1, ?)
                ON CONFLICT(token_fingerprint, consumer_id) DO UPDATE SET
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (fingerprint, consumer_id, now),
            )
            if prior_active != 1:
                activated += 1

        for (fingerprint, consumer_id), active in existing.items():
            if active != 1 or (fingerprint, consumer_id) in desired_pairs:
                continue
            conn.execute(
                """
                UPDATE telegram_bot_consumers
                SET active = 0, updated_at = ?
                WHERE token_fingerprint = ? AND consumer_id = ?
                """,
                (now, fingerprint, consumer_id),
            )
            deactivated += 1

        inbox_tokens = {
            str(row["token_fingerprint"])
            for row in conn.execute(
                "SELECT DISTINCT token_fingerprint FROM telegram_bot_updates"
            ).fetchall()
        }
        known_tokens = inbox_tokens | {fingerprint for fingerprint, _ in existing} | set(desired)
        for fingerprint in sorted(known_tokens - set(desired)):
            active_row = conn.execute(
                """
                SELECT 1
                FROM telegram_bot_consumers
                WHERE token_fingerprint = ? AND active = 1
                LIMIT 1
                """,
                (fingerprint,),
            ).fetchone()
            if active_row is not None:
                continue
            deleted = conn.execute(
                "DELETE FROM telegram_bot_updates WHERE token_fingerprint = ?",
                (fingerprint,),
            )
            deleted_updates += max(0, int(deleted.rowcount))

    return {
        "desired_tokens": len(desired),
        "desired_consumers": len(desired_pairs),
        "activated": activated,
        "deactivated": deactivated,
        "deleted_updates": deleted_updates,
    }


def install_state_repo_hardening(state_repo_type: Type[Any]) -> None:
    """Install compatibility-preserving hardened StateRepo operations."""

    state_repo_type.record_file = _record_file_atomic
    state_repo_type.register_bot_consumer = _register_bot_consumer
    state_repo_type.acknowledge_bot_consumer = _acknowledge_bot_consumer
    state_repo_type.deactivate_bot_consumer = _deactivate_bot_consumer
    state_repo_type.get_bot_consumer_watermark = _get_bot_consumer_watermark
    state_repo_type.reconcile_bot_consumers = _reconcile_bot_consumers
