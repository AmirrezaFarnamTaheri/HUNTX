import logging
import json
from typing import Dict, Any, List, Optional, Set
import sqlite3

logger = logging.getLogger(__name__)


class StateRepo:
    _BLOB_DEPENDENT_FORMATS = (
        "opaque_bundle", "ovpn", "npv4", "ehi", "hc", "hat", "sip", "nm", "dark",
    )

    def __init__(self, db_connection):
        self.db = db_connection

    # Existing repository methods remain unchanged.

    def prune_old_data(self, days: int) -> Dict[str, Any]:
        """Remove expired state without deleting ownership records for live blobs."""
        res: Dict[str, Any] = {
            "seen_files": 0,
            "records": 0,
            "published_artifacts": 0,
            "raw_hashes": [],
        }
        try:
            with self.db.connect() as conn:
                placeholders = ",".join("?" for _ in self._BLOB_DEPENDENT_FORMATS)
                cutoff = f"-{days} days"
                protected = conn.execute(
                    f"""
                    SELECT DISTINCT source_file_hash
                    FROM records
                    WHERE record_type IN ({placeholders})
                      AND is_active = 1
                    """,
                    list(self._BLOB_DEPENDENT_FORMATS),
                ).fetchall()
                protected_hashes = {row[0] for row in protected}

                candidates = conn.execute(
                    """
                    SELECT DISTINCT raw_hash
                    FROM seen_files
                    WHERE ingested_at < datetime('now', ?)
                      AND status != 'pending'
                    """,
                    (cutoff,),
                ).fetchall()
                res["raw_hashes"] = [
                    row[0] for row in candidates if row[0] not in protected_hashes
                ]

                if protected_hashes:
                    marks = ",".join("?" for _ in protected_hashes)
                    conn.execute(
                        f"""
                        DELETE FROM seen_files
                        WHERE ingested_at < datetime('now', ?)
                          AND status != 'pending'
                          AND raw_hash NOT IN ({marks})
                        """,
                        [cutoff, *protected_hashes],
                    )
                else:
                    conn.execute(
                        "DELETE FROM seen_files WHERE ingested_at < datetime('now', ?) AND status != 'pending'",
                        (cutoff,),
                    )
                res["seen_files"] = conn.total_changes

                res["records"] = conn.execute(
                    "DELETE FROM records WHERE created_at < datetime('now', ?) AND is_active = 0",
                    (cutoff,),
                ).rowcount

                res["published_artifacts"] = conn.execute(
                    "DELETE FROM published_artifacts WHERE published_at < datetime('now', ?)",
                    (cutoff,),
                ).rowcount
        except Exception:
            logger.exception("Failed to prune old database records")
            raise
        return res
