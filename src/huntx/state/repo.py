import logging
import json
from typing import Dict, Any, List, Optional, Set
import sqlite3

logger = logging.getLogger(__name__)


class StateRepo:
    # Formats whose records reference raw blobs at build time (via blob_hash).
    # These must NOT have their raw blobs pruned while active records exist.
    _BLOB_DEPENDENT_FORMATS = (
        "opaque_bundle",
        "ovpn",
        "npv4",
        "ehi",
        "hc",
        "hat",
        "sip",
        "nm",
        "dark",
    )

    def __init__(self, db_connection):
        self.db = db_connection

    def get_processed_hashes(self) -> List[str]:
        """Return raw_hash values no longer needed by active blob records."""
        placeholders = ",".join("?" for _ in self._BLOB_DEPENDENT_FORMATS)
        with self.db.connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT DISTINCT sf.raw_hash
                FROM seen_files sf
                WHERE sf.status != 'pending'
                  AND sf.raw_hash NOT IN (
                      SELECT DISTINCT r.source_file_hash
                      FROM records r
                      WHERE r.record_type IN ({placeholders})
                        AND r.is_active = 1
                  )
                """,
                list(self._BLOB_DEPENDENT_FORMATS),
            )
            return [row["raw_hash"] for row in cursor.fetchall()]

    def prune_old_data(self, days: int) -> Dict[str, Any]:
        """Purge old state while never returning active blob dependencies."""
        raw_hashes: list[str] = []
        res: Dict[str, Any] = {
            "seen_files": 0,
            "records": 0,
            "published_artifacts": 0,
            "raw_hashes": raw_hashes,
        }
        try:
            with self.db.connect() as conn:
                placeholders = ",".join("?" for _ in self._BLOB_DEPENDENT_FORMATS)
                cursor = conn.execute(
                    f"""
                    SELECT DISTINCT sf.raw_hash
                    FROM seen_files sf
                    WHERE sf.ingested_at < datetime('now', ?)
                      AND sf.status != 'pending'
                      AND sf.raw_hash NOT IN (
                          SELECT DISTINCT r.source_file_hash
                          FROM records r
                          WHERE r.record_type IN ({placeholders})
                            AND r.is_active = 1
                      )
                    """,
                    [f"-{days} days", *self._BLOB_DEPENDENT_FORMATS],
                )
                raw_hashes = [row["raw_hash"] for row in cursor.fetchall()]
                res["raw_hashes"] = raw_hashes

                c = conn.execute(
                    "DELETE FROM seen_files WHERE ingested_at < datetime('now', ?) AND status != 'pending'",
                    (f"-{days} days",),
                )
                res["seen_files"] = c.rowcount

                c = conn.execute("DELETE FROM records WHERE created_at < datetime('now', ?)", (f"-{days} days",))
                res["records"] = c.rowcount

                c = conn.execute(
                    "DELETE FROM published_artifacts WHERE published_at < datetime('now', ?)",
                    (f"-{days} days",),
                )
                res["published_artifacts"] = c.rowcount

            logger.info(
                "Database pruned: %s seen_files, %s records, %s artifacts, %s raw candidates",
                res["seen_files"],
                res["records"],
                res["published_artifacts"],
                len(res["raw_hashes"]),
            )
        except Exception as exc:
            logger.error("Failed to prune old database records: %s", exc)
            raise
        return res
