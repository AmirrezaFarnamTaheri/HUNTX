"""Read-only, bounded, provenance-aware corpus sampling shared by reporters."""
from __future__ import annotations

import sqlite3
from pathlib import Path


_MAX_SCAN = 50_000


def load_active_observations(
    db_path: Path, *, limit: int
) -> tuple[list[tuple[str, str]], bool] | None:
    """Read only active, successfully processed NPVT observations.

    An absent, locked or invalid state database returns unavailable rather
    than a fabricated empty fleet. Truncation is explicit and deterministic.
    """
    if not db_path.is_file() or type(limit) is not int or not 1 <= limit <= _MAX_SCAN:
        return None
    try:
        connection = sqlite3.connect(
            "file:" + db_path.resolve().as_posix() + "?mode=ro",
            uri=True, timeout=8,
        )
        try:
            rows = connection.execute(
                "SELECT s.source_id, r.data_json "
                "FROM records r "
                "JOIN seen_files s ON s.id = r.source_observation_id "
                "WHERE r.is_active = 1 AND r.record_type = 'npvt' "
                "AND s.status = 'processed' "
                "ORDER BY r.id DESC LIMIT ?",
                (limit + 1,),
            ).fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        return None
    return (
        [(str(source_id), str(data)) for source_id, data in rows[:limit]],
        len(rows) > limit,
    )
