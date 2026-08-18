from __future__ import annotations

import json
import math
import time
from typing import Any, Optional

_EVENT_COLUMNS = {
    "attempt": "last_attempt_at",
    "transport_success": "last_transport_success_at",
    "nonempty": "last_nonempty_at",
    "valid": "last_valid_at",
    "published": "last_published_at",
}
_TRUST_STATES = {"candidate", "approved", "degraded", "quarantined", "retired"}
_ALLOWED_TRUST_TRANSITIONS = {
    "candidate": {"candidate", "approved", "quarantined", "retired"},
    "approved": {"approved", "degraded", "quarantined", "retired"},
    "degraded": {"degraded", "approved", "quarantined", "retired"},
    "quarantined": {"quarantined", "candidate", "retired"},
    "retired": {"retired"},
}


def record_source_event(
    db: Any,
    source_id: str,
    source_type: str,
    trust_state: str,
    event: str,
    *,
    observed_at: Optional[float] = None,
    error_code: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    if event not in _EVENT_COLUMNS and event != "failure":
        raise ValueError(f"Unknown lifecycle event: {event}")
    if trust_state not in _TRUST_STATES:
        raise ValueError(f"Unknown source trust state: {trust_state}")
    now = float(observed_at if observed_at is not None else time.time())
    if not math.isfinite(now):
        raise ValueError("observed_at must be finite")
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM source_lifecycle WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if existing is not None:
            current_trust = str(existing["trust_state"])
            is_latest_event = now >= float(existing["updated_at"])
            if is_latest_event and trust_state not in _ALLOWED_TRUST_TRANSITIONS[current_trust]:
                raise ValueError(f"Illegal source trust transition: {current_trust} -> " f"{trust_state}")
        else:
            is_latest_event = True

        conn.execute(
            """
            INSERT INTO source_lifecycle
                (source_id, source_type, trust_state, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_type=CASE
                    WHEN excluded.updated_at >= source_lifecycle.updated_at
                    THEN excluded.source_type
                    ELSE source_lifecycle.source_type
                END,
                trust_state=CASE
                    WHEN excluded.updated_at >= source_lifecycle.updated_at
                    THEN excluded.trust_state
                    ELSE source_lifecycle.trust_state
                END,
                updated_at=MAX(source_lifecycle.updated_at, excluded.updated_at),
                metadata_json=CASE
                    WHEN excluded.updated_at >= source_lifecycle.updated_at
                    THEN excluded.metadata_json
                    ELSE source_lifecycle.metadata_json
                END
            """,
            (source_id, source_type, trust_state, now, json.dumps(metadata or {}, sort_keys=True)),
        )
        timestamp_column = _EVENT_COLUMNS.get(event)
        if timestamp_column:
            conn.execute(
                f"""
                UPDATE source_lifecycle
                SET {timestamp_column} = MAX(COALESCE({timestamp_column}, ?), ?),
                    updated_at = MAX(updated_at, ?)
                WHERE source_id = ?
                """,
                (now, now, now, source_id),
            )
        if is_latest_event and event in {"transport_success", "nonempty", "valid", "published"}:
            conn.execute(
                "UPDATE source_lifecycle SET consecutive_failures = 0, last_error_code = NULL WHERE source_id = ?",
                (source_id,),
            )
        elif is_latest_event and event == "failure":
            conn.execute(
                """
                UPDATE source_lifecycle
                SET consecutive_failures = consecutive_failures + 1,
                    last_error_code = ?, updated_at = ?
                WHERE source_id = ?
                """,
                (error_code or "SOURCE_FAILURE", now, source_id),
            )


def get_source_lifecycle(db: Any, source_id: str) -> Optional[dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM source_lifecycle WHERE source_id = ?", (source_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    return result
