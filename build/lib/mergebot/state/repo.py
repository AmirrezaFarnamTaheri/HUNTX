import json
import logging
from typing import Optional, Dict, Any, List
from .db import DBConnection

logger = logging.getLogger(__name__)

class StateRepo:
    def __init__(self, db: DBConnection):
        self.db = db

    def get_source_state(self, source_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT state_json FROM sources WHERE id = ?", (source_id,)
                ).fetchone()
                if row and row["state_json"]:
                    return json.loads(row["state_json"])
            return None
        except Exception as e:
            logger.error(f"Failed to get source state for {source_id}: {e}")
            return None

    def update_source_state(self, source_id: str, state: Dict[str, Any], source_type: str = "unknown"):
        try:
            state_json = json.dumps(state)
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sources (id, type, state_json, last_check_ts)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        state_json = excluded.state_json,
                        last_check_ts = CURRENT_TIMESTAMP
                    """,
                    (source_id, source_type, state_json)
                )
            # logger.debug(f"Updated source state for {source_id}")
        except Exception as e:
            logger.exception(f"Failed to update source state for {source_id}: {e}")

    def has_seen_file(self, source_id: str, external_id: str) -> bool:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM seen_files WHERE source_id = ? AND external_id = ?",
                    (source_id, str(external_id))
                ).fetchone()
                return bool(row)
        except Exception as e:
            logger.error(f"Error checking seen file {external_id} from {source_id}: {e}")
            return False

    def record_file(self, source_id: str, external_id: str, raw_hash: str, file_size: int, filename: str, status: str = "pending", metadata: Dict[str, Any] = {}):
        try:
            metadata_json = json.dumps(metadata)
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO seen_files (source_id, external_id, raw_hash, file_size, filename, status, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source_id, str(external_id), raw_hash, file_size, filename, status, metadata_json)
                )
            logger.debug(f"Recorded file {filename} (ID: {external_id}) from {source_id}")
        except Exception as e:
            logger.exception(f"Failed to record file {filename}: {e}")

    def update_file_status(self, raw_hash: str, status: str, error_msg: Optional[str] = None):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE seen_files SET status = ?, error_msg = ? WHERE raw_hash = ?",
                    (status, error_msg, raw_hash)
                )
            # logger.debug(f"Updated status for {raw_hash} to {status}")
        except Exception as e:
            logger.error(f"Failed to update status for {raw_hash}: {e}")

    def get_pending_files(self) -> List[Dict[str, Any]]:
        try:
            with self.db.connect() as conn:
                cursor = conn.execute(
                    "SELECT id, source_id, external_id, raw_hash, filename FROM seen_files WHERE status = 'pending'"
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pending files: {e}")
            return []

    def add_record(self, raw_hash: str, record_type: str, unique_hash: str, data: Dict[str, Any]):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO records (source_file_hash, record_type, unique_hash, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (raw_hash, record_type, unique_hash, json.dumps(data))
                )
        except Exception as e:
            logger.exception(f"Failed to add record {unique_hash}: {e}")

    def get_records_for_build(self, record_types: List[str], allowed_source_ids: List[str]) -> List[Dict[str, Any]]:
        if not record_types or not allowed_source_ids:
            return []

        try:
            # Dynamically build query placeholders
            placeholders_types = ",".join("?" for _ in record_types)
            placeholders_sources = ",".join("?" for _ in allowed_source_ids)

            query = f"""
                SELECT r.data_json
                FROM records r
                JOIN seen_files s ON r.source_file_hash = s.raw_hash
                WHERE r.record_type IN ({placeholders_types})
                  AND s.source_id IN ({placeholders_sources})
                  AND r.is_active = 1
                GROUP BY r.unique_hash
                ORDER BY r.created_at ASC
            """

            args = record_types + allowed_source_ids

            with self.db.connect() as conn:
                cursor = conn.execute(query, args)
                return [json.loads(row["data_json"]) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get records for build (types={record_types}): {e}")
            return []

    def is_artifact_published(self, route_name: str, artifact_hash: str) -> bool:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT 1 FROM published_artifacts
                    WHERE route_name = ? AND artifact_hash = ?
                    """,
                    (route_name, artifact_hash)
                ).fetchone()
                return bool(row)
        except Exception as e:
            logger.error(f"Error checking if artifact published: {e}")
            return False

    def mark_published(self, route_name: str, artifact_hash: str, metadata: Dict[str, Any] = {}):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO published_artifacts (route_name, artifact_hash, metadata_json)
                    VALUES (?, ?, ?)
                    """,
                    (route_name, artifact_hash, json.dumps(metadata))
                )
            logger.info(f"Marked artifact {artifact_hash} as published for {route_name}")
        except Exception as e:
            logger.exception(f"Failed to mark published artifact: {e}")

    def get_last_published_hash(self, route_name: str) -> Optional[str]:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT artifact_hash FROM published_artifacts
                    WHERE route_name = ?
                    ORDER BY published_at DESC LIMIT 1
                    """,
                    (route_name,)
                ).fetchone()
                return row["artifact_hash"] if row else None
        except Exception as e:
            logger.error(f"Failed to get last published hash for {route_name}: {e}")
            return None
