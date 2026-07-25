from __future__ import annotations

import json
import time
from typing import Any, Optional

_EVENT_COLUMNS = {
    "attempt": "last_attempt_at",
    "transport_success": "last_transport_success_at",
    "nonempty": "last_nonempty_at",
    "valid": "last_valid_at",
    "published": "last_published_at",
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
    now = float(observed_at if observed_at is not None else time.time())
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO source_lifecycle
                (source_id, source_type, trust_state, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_type=excluded.source_type,
                trust_state=excluded.trust_state,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (source_id, source_type, trust_state, now, json.dumps(metadata or {}, sort_keys=True)),
        )
        timestamp_column = _EVENT_COLUMNS.get(event)
        if timestamp_column:
            conn.execute(
                f"UPDATE source_lifecycle SET {timestamp_column} = ?, updated_at = ? WHERE source_id = ?",
                (now, now, source_id),
            )
        if event in {"transport_success", "nonempty", "valid", "published"}:
            conn.execute(
                "UPDATE source_lifecycle SET consecutive_failures = 0, last_error_code = NULL WHERE source_id = ?",
                (source_id,),
            )
        elif event == "failure":
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
