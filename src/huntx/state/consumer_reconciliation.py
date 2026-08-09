from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Mapping, Set as AbstractSet
from typing import Any, Dict, Set, Type


def _validate_fingerprint(value: str) -> str:
    fingerprint = str(value)
    if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
        raise ValueError("token_fingerprint must be a lowercase SHA-256 digest")
    return fingerprint


def _validate_consumer_id(value: str) -> str:
    consumer_id = str(value).strip()
    if not consumer_id:
        raise ValueError("consumer_id is required")
    if len(consumer_id) > 512:
        raise ValueError("consumer_id is too long")
    return consumer_id


def _normalize_desired(desired_consumers: Mapping[str, AbstractSet[str]]) -> Dict[str, Set[str]]:
    normalized: Dict[str, Set[str]] = {}
    for raw_fingerprint, raw_consumers in desired_consumers.items():
        fingerprint = _validate_fingerprint(raw_fingerprint)
        if isinstance(raw_consumers, (str, bytes)):
            raise ValueError("consumer collection must be set-like")
        normalized[fingerprint] = {_validate_consumer_id(value) for value in raw_consumers}
    return normalized


def reconcile_bot_consumers(
    self: Any,
    desired_consumers: Mapping[str, AbstractSet[str]],
    *,
    authoritative: bool,
) -> Dict[str, int]:
    """Reconcile Bot API consumers without resetting durable watermarks.

    ``authoritative=False`` is the safety mode for temporarily incomplete
    credential/configuration resolution: desired consumers are activated, but
    no existing consumer is deactivated and no inbox row is purged. When the
    configuration is authoritative, removed consumers are deactivated in the
    same transaction and inbox rows are purged only for tokens with no active
    consumer remaining.
    """

    desired = _normalize_desired(desired_consumers)
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
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT token_fingerprint, consumer_id, active
            FROM telegram_bot_consumers
            """
        ).fetchall()
        existing = {
            (str(row["token_fingerprint"]), str(row["consumer_id"])): int(row["active"])
            for row in rows
        }

        for fingerprint, consumer_id in sorted(desired_pairs):
            was_active = existing.get((fingerprint, consumer_id)) == 1
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
            if not was_active:
                activated += 1

        if authoritative:
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
                active = conn.execute(
                    """
                    SELECT 1
                    FROM telegram_bot_consumers
                    WHERE token_fingerprint = ? AND active = 1
                    LIMIT 1
                    """,
                    (fingerprint,),
                ).fetchone()
                if active is not None:
                    continue
                deleted = conn.execute(
                    "DELETE FROM telegram_bot_updates WHERE token_fingerprint = ?",
                    (fingerprint,),
                )
                deleted_updates += max(0, int(deleted.rowcount))

    return {
        "authoritative": int(authoritative),
        "desired_tokens": len(desired),
        "desired_consumers": len(desired_pairs),
        "activated": activated,
        "deactivated": deactivated,
        "deleted_updates": deleted_updates,
    }


def reconcile_configured_bot_consumers(repo: Any, config: Any) -> Dict[str, int]:
    """Reconcile durable consumers from the fully validated runtime config."""

    desired: Dict[str, Set[str]] = {}
    authoritative = True
    configured_sources = 0
    resolved_sources = 0

    for source in config.sources:
        telegram = getattr(source, "telegram", None)
        if getattr(source, "type", None) != "telegram" or telegram is None:
            continue
        configured_sources += 1
        token = (getattr(telegram, "token", None) or os.environ.get("TELEGRAM_TOKEN", "")).strip()
        if not token or ":" not in token:
            authoritative = False
            continue
        fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()
        desired.setdefault(fingerprint, set()).add(f"chat:{telegram.chat_id}")
        resolved_sources += 1

    result = repo.reconcile_bot_consumers(desired, authoritative=authoritative)
    result["configured_sources"] = configured_sources
    result["resolved_sources"] = resolved_sources
    return result


def install_consumer_reconciliation(state_repo_type: Type[Any]) -> None:
    state_repo_type.reconcile_bot_consumers = reconcile_bot_consumers
