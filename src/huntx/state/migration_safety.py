from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Type

from .db import _canonicalize_vmess_line


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _obsolete_vmess_hashes(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "records"):
        return set()
    obsolete: set[str] = set()
    rows = conn.execute(
        """
        SELECT unique_hash, data_json
        FROM records
        WHERE record_type IN ('npvt', 'npvtsub')
          AND data_json IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        try:
            data = json.loads(row["data_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("line"), str):
            continue
        canonical = _canonicalize_vmess_line(data["line"])
        if canonical is None:
            continue
        new_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        old_hash = str(row["unique_hash"])
        if data["line"] != canonical or old_hash != new_hash:
            obsolete.add(old_hash)
    return obsolete


def install_migration_safety(db_connection_type: Type[Any]) -> None:
    """Preserve verdict cache rows unrelated to the v10 VMess re-keying.

    The original v10 migration removes every verdict not referenced by a record.
    That is broader than the migration's authority: probe/policy verdicts may be
    cached before their record is observed again. Snapshotting all non-obsolete
    rows before the migration and restoring them afterwards narrows deletion to
    only the legacy VMess hashes that were actually re-keyed.
    """

    if getattr(db_connection_type, "_migration_safety_applied", False):
        return
    original = db_connection_type._check_migrations

    def hardened_check_migrations(self: Any, conn: sqlite3.Connection) -> None:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        columns: list[str] = []
        preserved: list[tuple[Any, ...]] = []
        if version < 10 and _table_exists(conn, "record_verdicts"):
            obsolete = _obsolete_vmess_hashes(conn)
            columns = [
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(record_verdicts)").fetchall()
            ]
            if columns:
                quoted = ", ".join(f'"{column}"' for column in columns)
                query = f"SELECT {quoted} FROM record_verdicts"
                parameters: tuple[str, ...] = ()
                if obsolete:
                    placeholders = ", ".join("?" for _ in obsolete)
                    query += f" WHERE unique_hash NOT IN ({placeholders})"
                    parameters = tuple(sorted(obsolete))
                preserved = [
                    tuple(row[column] for column in columns)
                    for row in conn.execute(query, parameters).fetchall()
                ]

        original(self, conn)

        if columns and preserved:
            quoted = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(
                f"INSERT OR IGNORE INTO record_verdicts ({quoted}) VALUES ({placeholders})",
                preserved,
            )

    db_connection_type._check_migrations = hardened_check_migrations
    db_connection_type._migration_safety_applied = True
