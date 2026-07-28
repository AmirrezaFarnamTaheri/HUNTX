import logging
import json
from typing import Dict, Any, List, Optional, Set
import sqlite3
import time

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

    def get_source_state(self, source_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        try:
            if conn:
                cursor = conn.execute("SELECT state_json FROM source_state WHERE source_id = ?", (source_id,))
                row = cursor.fetchone()
                return json.loads(row["state_json"]) if row else None
            else:
                with self.db.connect() as c:
                    return self.get_source_state(source_id, c)
        except Exception as e:
            logger.error(f"Failed to get source state for {source_id}: {e}")
            raise

    def update_source_state(
        self,
        source_id: str,
        state: Dict[str, Any],
        source_type: str = "telegram",
        conn: Optional[sqlite3.Connection] = None,
    ):
        try:
            state_json = json.dumps(state)
            if conn:
                conn.execute(
                    """
                    INSERT INTO source_state (source_id, source_type, state_json, updated_at)
                    VALUES (?, ?, ?, strftime('%s', 'now'))
                    ON CONFLICT(source_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (source_id, source_type, state_json),
                )
            else:
                with self.db.connect() as c:
                    self.update_source_state(source_id, state, source_type, c)
        except Exception as e:
            logger.error(f"Failed to update source state for {source_id}: {e}")
            raise

    def store_bot_updates(
        self,
        token_fingerprint: str,
        updates: List[Dict[str, Any]],
    ) -> None:
        """Durably stage Bot API responses before their server acknowledgement."""
        if len(token_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in token_fingerprint):
            raise ValueError("token_fingerprint must be a lowercase SHA-256 digest")
        normalized = []
        now = time.time()
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or isinstance(update_id, bool):
                raise ValueError("Telegram update_id must be an integer")
            normalized.append(
                (
                    token_fingerprint,
                    update_id,
                    json.dumps(update, separators=(",", ":"), sort_keys=True),
                    now,
                )
            )
        if not normalized:
            return
        with self.db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO telegram_bot_updates
                    (token_fingerprint, update_id, payload_json, received_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(token_fingerprint, update_id) DO NOTHING
                """,
                normalized,
            )

    def get_bot_update_max_id(self, token_fingerprint: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(update_id), 0) AS max_id
                FROM telegram_bot_updates
                WHERE token_fingerprint = ?
                """,
                (token_fingerprint,),
            ).fetchone()
            max_id = row["max_id"] if row else 0
            return int(str(max_id)) if max_id is not None else 0

    def get_bot_updates_after(
        self,
        token_fingerprint: str,
        update_id: int,
    ) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM telegram_bot_updates
                WHERE token_fingerprint = ? AND update_id > ?
                ORDER BY update_id ASC
                """,
                (token_fingerprint, int(update_id)),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def has_seen_file(self, source_id: str, external_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        try:
            query = "SELECT 1 FROM seen_files WHERE source_id = ? AND external_id = ?"
            args = (source_id, str(external_id))

            if conn:
                return bool(conn.execute(query, args).fetchone())
            else:
                with self.db.connect() as c:
                    return bool(c.execute(query, args).fetchone())
        except Exception as e:
            logger.error(f"Error checking seen file {external_id} from {source_id}: {e}")
            raise

    def record_file(
        self,
        source_id: str,
        external_id: str,
        raw_hash: str,
        file_size: int,
        filename: str,
        status: str = "pending",
        metadata: Optional[Dict[str, Any]] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        try:
            metadata_json = json.dumps(metadata or {})
            external_id = str(external_id)

            def _record(c: sqlite3.Connection) -> int:
                existing = c.execute(
                    """
                    SELECT id, raw_hash FROM seen_files
                    WHERE source_id = ? AND external_id = ?
                    """,
                    (source_id, external_id),
                ).fetchone()
                if existing is None:
                    cursor = c.execute(
                        """
                        INSERT INTO seen_files
                            (source_id, external_id, raw_hash, file_size, filename,
                             status, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source_id,
                            external_id,
                            raw_hash,
                            file_size,
                            filename,
                            status,
                            metadata_json,
                        ),
                    )
                    if cursor.lastrowid is None:
                        raise RuntimeError("SQLite did not return an observation id")
                    return int(cursor.lastrowid)

                observation_id = int(existing["id"])
                if existing["raw_hash"] != raw_hash:
                    c.execute(
                        """
                        UPDATE records SET is_active = 0
                        WHERE source_observation_id = ? AND is_active = 1
                        """,
                        (observation_id,),
                    )
                    c.execute(
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
                return observation_id

            if conn:
                observation_id = _record(conn)
            else:
                with self.db.connect() as c:
                    observation_id = _record(c)

            logger.debug(f"Recorded file {filename} (ID: {external_id}) from {source_id}")
            return observation_id
        except Exception as e:
            logger.exception(f"Failed to record file {filename}: {e}")
            raise

    def get_seen_files_batch(
        self, source_id: str, external_ids: List[str], conn: Optional[sqlite3.Connection] = None
    ) -> Set[str]:
        if not external_ids:
            return set()

        try:
            placeholders = ",".join("?" for _ in external_ids)
            query = f"SELECT external_id FROM seen_files WHERE source_id = ? AND external_id IN ({placeholders})"
            args = [source_id] + external_ids

            if conn:
                cursor = conn.execute(query, args)
                return {row[0] for row in cursor.fetchall()}
            else:
                with self.db.connect() as c:
                    cursor = c.execute(query, args)
                    return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get seen files batch for {source_id}: {e}")
            raise

    def get_seen_file_hashes_batch(
        self,
        source_id: str,
        external_ids: List[str],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, str]:
        if not external_ids:
            return {}
        placeholders = ",".join("?" for _ in external_ids)
        query = (
            "SELECT external_id, raw_hash FROM seen_files " f"WHERE source_id = ? AND external_id IN ({placeholders})"
        )
        args = [source_id, *[str(item) for item in external_ids]]
        if conn:
            rows = conn.execute(query, args).fetchall()
        else:
            with self.db.connect() as c:
                rows = c.execute(query, args).fetchall()
        return {str(row["external_id"]): str(row["raw_hash"]) for row in rows}

    def record_files_batch(self, records: List[tuple], conn: Optional[sqlite3.Connection] = None):
        if not records:
            return

        try:

            def _record_all(c: sqlite3.Connection) -> None:
                for row in records:
                    metadata = json.loads(row[6]) if isinstance(row[6], str) else row[6]
                    self.record_file(
                        row[0],
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        metadata,
                        conn=c,
                    )

            if conn:
                _record_all(conn)
            else:
                with self.db.connect() as c:
                    _record_all(c)
            logger.debug(f"Batch-recorded {len(records)} files.")
        except Exception as e:
            logger.exception(f"Failed to batch-record files: {e}")
            raise

    def update_file_status(self, raw_hash: str, status: str, error_msg: Optional[str] = None):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE seen_files SET status = ?, error_msg = ? WHERE raw_hash = ?",
                    (status, error_msg, raw_hash),
                )
        except Exception as e:
            logger.error(f"Failed to update status for {raw_hash}: {e}")
            raise

    def update_observation_status(
        self,
        observation_id: int,
        status: str,
        error_msg: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        sql = "UPDATE seen_files SET status = ?, error_msg = ? WHERE id = ?"
        args = (status, error_msg, observation_id)
        if conn:
            conn.execute(sql, args)
        else:
            with self.db.connect() as c:
                c.execute(sql, args)

    def get_pending_files(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            sql = "SELECT id, source_id, external_id, raw_hash, filename, file_size FROM seen_files WHERE status = 'pending' ORDER BY id ASC"
            args = []
            if limit:
                sql += " LIMIT ?"
                args.append(limit)
            with self.db.connect() as conn:
                cursor = conn.execute(sql, args)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pending files: {e}")
            raise

    def add_record(self, raw_hash: str, record_type: str, unique_hash: str, data: Dict[str, Any]):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO records (source_file_hash, record_type, unique_hash, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (raw_hash, record_type, unique_hash, json.dumps(data)),
                )
        except Exception as e:
            logger.exception(f"Failed to add record {unique_hash}: {e}")
            raise

    def add_records_batch(self, rows: List[tuple], conn: Optional[sqlite3.Connection] = None):
        """Batch insert records with exact observation provenance.

        Preferred rows are ``(raw_hash, observation_id, record_type,
        unique_hash, data_json_str)``. Four-field legacy rows remain accepted
        during migration and receive a null observation identity.

        Pass ``conn`` to enlist in a caller-owned transaction. The transform
        pipeline must do so: inserting records and flipping the source files out
        of 'pending' has to be atomic, or a crash between the two commits leaves
        records durable while their files still look unprocessed, so the next
        run re-parses and re-inserts them (unbounded `records` growth).
        """
        if not rows:
            return
        try:
            if any(len(row) not in {4, 5} for row in rows):
                raise ValueError("record rows must contain four or five fields")
            normalized = [row if len(row) == 5 else (row[0], None, row[1], row[2], row[3]) for row in rows]
            sql = """
                INSERT INTO records
                    (source_file_hash, source_observation_id, record_type,
                     unique_hash, data_json)
                VALUES (?, ?, ?, ?, ?)
            """
            if conn:
                conn.executemany(sql, normalized)
            else:
                with self.db.connect() as c:
                    c.executemany(sql, normalized)
            logger.debug(f"Batch-inserted {len(rows)} records.")
        except Exception as e:
            logger.exception(f"Failed to batch-insert {len(rows)} records: {e}")
            raise  # Re-raise so the pipeline knows it failed

    def update_file_status_batch(self, updates: List[tuple], conn: Optional[sqlite3.Connection] = None):
        """Batch update file statuses. Each item is (status, error_msg, raw_hash).

        Pass ``conn`` to enlist in a caller-owned transaction — see
        :meth:`add_records_batch` for why the transform pipeline requires it.
        """
        if not updates:
            return
        try:
            sql = "UPDATE seen_files SET status = ?, error_msg = ? WHERE raw_hash = ?"
            if conn:
                conn.executemany(sql, updates)
            else:
                with self.db.connect() as c:
                    c.executemany(sql, updates)
            logger.debug(f"Batch-updated status for {len(updates)} files.")
        except Exception as e:
            logger.error(f"Failed to batch-update file statuses: {e}")
            raise  # Re-raise to prevent infinite loops if status update fails

    def update_observation_status_batch(
        self,
        updates: List[tuple],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Update exact observations. Each item is (status, error_msg, id)."""
        if not updates:
            return
        sql = "UPDATE seen_files SET status = ?, error_msg = ? WHERE id = ?"
        if conn:
            conn.executemany(sql, updates)
        else:
            with self.db.connect() as c:
                c.executemany(sql, updates)

    def get_records_for_build(
        self,
        record_types: List[str],
        allowed_source_ids: List[str],
        min_seen_file_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not record_types or not allowed_source_ids:
            return []

        try:
            placeholders_types = ",".join("?" for _ in record_types)
            placeholders_sources = ",".join("?" for _ in allowed_source_ids)
            where_extra = ""
            args: List[Any] = list(record_types) + list(allowed_source_ids)
            if min_seen_file_id is not None:
                where_extra = " AND s.id > ?"
                args.append(int(min_seen_file_id))

            # DISTINCT is required, not cosmetic: seen_files.raw_hash is NOT
            # unique (only UNIQUE(source_id, external_id) is enforced), so the
            # same content seen in N allowed sources produces N seen_files rows
            # and this JOIN fans one record out to N identical rows. The dedup
            # CTE below groups by (record_type, unique_hash) and keeps MAX(id),
            # but the final join then re-matches every fanned-out row carrying
            # that id — re-emitting the record N times into the built artifact
            # (duplicate proxy lines and inflated counts). Every selected column
            # comes from `records`, so DISTINCT collapses the fan-out exactly.
            query = f"""
                WITH filtered AS (
                    SELECT DISTINCT r.id, r.record_type, r.unique_hash, r.data_json
                    FROM records r
                    JOIN seen_files s ON (
                        r.source_observation_id = s.id
                        OR (
                            r.source_observation_id IS NULL
                            AND r.source_file_hash = s.raw_hash
                        )
                    )
                    WHERE r.record_type IN ({placeholders_types})
                      AND s.source_id IN ({placeholders_sources})
                      AND r.is_active = 1
                      {where_extra}
                ),
                dedup AS (
                    SELECT record_type, unique_hash, MAX(id) AS keep_id
                    FROM filtered
                    GROUP BY record_type, unique_hash
                )
                SELECT f.record_type, f.data_json
                FROM filtered f
                JOIN dedup d ON d.keep_id = f.id
                ORDER BY f.id ASC
            """

            with self.db.connect() as conn:
                cursor = conn.execute(query, args)
                return [
                    {"record_type": row["record_type"], "data": json.loads(row["data_json"])}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to get records for build (types={record_types}): {e}")
            raise

    def is_artifact_published(self, route_name: str, artifact_hash: str) -> bool:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT 1 FROM published_artifacts
                    WHERE route_name = ? AND artifact_hash = ?
                    """,
                    (route_name, artifact_hash),
                ).fetchone()
                return bool(row)
        except Exception as e:
            logger.error(f"Error checking if artifact published: {e}")
            raise

    def mark_published(self, route_name: str, artifact_hash: str, metadata: Optional[Dict[str, Any]] = None):
        try:
            metadata_json = json.dumps(metadata or {})
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO published_artifacts (route_name, artifact_hash, metadata_json)
                    VALUES (?, ?, ?)
                    """,
                    (route_name, artifact_hash, metadata_json),
                )
            logger.info(f"Marked artifact {artifact_hash} as published for {route_name}")
        except Exception as e:
            logger.exception(f"Failed to mark published artifact: {e}")
            raise

    def ensure_publication_intent(
        self,
        publication_key: str,
        artifact_hash: str,
        *,
        generation: str,
    ) -> int:
        """Return the durable identity for one artifact/config generation."""
        if not publication_key or not generation:
            raise ValueError("publication_key and generation are required")
        if len(artifact_hash) != 64 or any(c not in "0123456789abcdef" for c in artifact_hash):
            raise ValueError("artifact_hash must be a lowercase SHA-256 digest")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO publication_intents
                    (publication_key, artifact_hash, generation, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(publication_key, artifact_hash, generation) DO NOTHING
                """,
                (publication_key, artifact_hash, generation, time.time()),
            )
            row = conn.execute(
                """
                SELECT id FROM publication_intents
                WHERE publication_key = ? AND artifact_hash = ? AND generation = ?
                """,
                (publication_key, artifact_hash, generation),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to create publication intent")
            return int(row["id"])

    def is_delivery_confirmed(self, intent_id: int, destination_id: str) -> bool:
        with self.db.connect() as conn:
            return (
                conn.execute(
                    """
                    SELECT 1 FROM publication_deliveries
                    WHERE intent_id = ? AND destination_id = ? AND state = 'confirmed'
                    """,
                    (intent_id, destination_id),
                ).fetchone()
                is not None
            )

    def get_delivery_state(
        self,
        intent_id: int,
        destination_id: str,
    ) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT state FROM publication_deliveries
                WHERE intent_id = ? AND destination_id = ?
                """,
                (intent_id, destination_id),
            ).fetchone()
        return str(row["state"]) if row else None

    def mark_delivery_sending(self, intent_id: int, destination_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO publication_deliveries
                    (intent_id, destination_id, state, attempt_count, last_attempt_at)
                VALUES (?, ?, 'sending', 1, ?)
                ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                    state='sending',
                    attempt_count=publication_deliveries.attempt_count + 1,
                    last_attempt_at=excluded.last_attempt_at,
                    error_class=NULL
                WHERE publication_deliveries.state != 'confirmed'
                """,
                (intent_id, destination_id, time.time()),
            )

    def mark_delivery_confirmed(
        self,
        intent_id: int,
        destination_id: str,
        *,
        remote_receipt: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO publication_deliveries
                    (intent_id, destination_id, state, attempt_count,
                     last_attempt_at, confirmed_at, remote_receipt)
                VALUES (?, ?, 'confirmed', 1, ?, ?, ?)
                ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                    state='confirmed',
                    confirmed_at=excluded.confirmed_at,
                    remote_receipt=COALESCE(
                        excluded.remote_receipt,
                        publication_deliveries.remote_receipt
                    ),
                    error_class=NULL
                """,
                (intent_id, destination_id, now, now, remote_receipt),
            )

    def mark_delivery_failed(
        self,
        intent_id: int,
        destination_id: str,
        *,
        error_class: str,
        unknown_outcome: bool = False,
    ) -> None:
        state = "unknown_outcome" if unknown_outcome else "failed"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO publication_deliveries
                    (intent_id, destination_id, state, attempt_count,
                     last_attempt_at, error_class)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                    state=excluded.state,
                    last_attempt_at=excluded.last_attempt_at,
                    error_class=excluded.error_class
                WHERE publication_deliveries.state != 'confirmed'
                """,
                (intent_id, destination_id, state, time.time(), error_class),
            )

    def complete_publication_intent(self, intent_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE publication_intents SET completed_at = ? WHERE id = ?",
                (time.time(), intent_id),
            )

    def get_processed_hashes(self) -> List[str]:
        """Return raw_hash values for files that are no longer pending
        AND are not still needed by active blob-dependent records."""
        try:
            placeholders = ",".join("?" for _ in self._BLOB_DEPENDENT_FORMATS)
            with self.db.connect() as conn:
                if placeholders:
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
                else:
                    cursor = conn.execute("SELECT DISTINCT raw_hash FROM seen_files WHERE status != 'pending'")
                return [row["raw_hash"] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get processed hashes: {e}")
            raise

    def get_all_known_hashes(self) -> set:
        """Return all raw hashes tracked in the seen_files table."""
        try:
            with self.db.connect() as conn:
                cursor = conn.execute("SELECT DISTINCT raw_hash FROM seen_files")
                return {row["raw_hash"] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get all known hashes: {e}")
            raise

    def get_last_published_hash(self, route_name: str) -> Optional[str]:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT artifact_hash FROM published_artifacts
                    WHERE route_name = ?
                    ORDER BY published_at DESC, id DESC LIMIT 1
                    """,
                    (route_name,),
                ).fetchone()
                return row["artifact_hash"] if row else None
        except Exception as e:
            logger.error(f"Failed to get last published hash for {route_name}: {e}")
            raise

    def prune_old_data(self, days: int) -> Dict[str, Any]:
        """Purge seen_files, records, and published_artifacts older than N days.
        Returns a dict summarizing the counts of pruned entries and deleted raw_hashes."""
        raw_hashes: list[str] = []
        res: Dict[str, Any] = {"seen_files": 0, "records": 0, "published_artifacts": 0, "raw_hashes": raw_hashes}
        try:
            with self.db.connect() as conn:
                # A raw blob must NOT be pruned while an active blob-dependent
                # record (ovpn/ehi/hc/…) still reads it at build time. This is
                # the same guard get_processed_hashes() applies; without it,
                # prune deletes a live-referenced blob (and its seen_files
                # tracking row) and the next route build yields a corrupt or
                # empty artifact with no recovery. The reference timelines
                # legitimately diverge — e.g. a file ingested >N days ago but
                # transformed recently has an old seen_files.ingested_at yet a
                # fresh, still-active record.
                blob_formats = list(self._BLOB_DEPENDENT_FORMATS)
                placeholders = ",".join("?" for _ in blob_formats)
                if placeholders:
                    still_referenced = (
                        f"raw_hash NOT IN ("
                        f"SELECT DISTINCT r.source_file_hash FROM records r "
                        f"WHERE r.record_type IN ({placeholders}) AND r.is_active = 1)"
                    )
                    ref_params = blob_formats
                else:
                    still_referenced = "1=1"
                    ref_params = []

                age_clause = "ingested_at < datetime('now', ?) AND status != 'pending'"

                # 1. Raw hashes eligible for blob deletion: old, non-pending,
                #    and not still referenced by an active blob-dependent record.
                cursor = conn.execute(
                    f"SELECT DISTINCT raw_hash FROM seen_files " f"WHERE {age_clause} AND {still_referenced}",
                    (f"-{days} days", *ref_params),
                )
                raw_hashes = [row["raw_hash"] for row in cursor.fetchall()]
                res["raw_hashes"] = raw_hashes

                # 2. Delete seen_files — but keep the tracking row for any blob
                #    still referenced by an active record, so get_all_known_hashes
                #    continues to protect it from prune_orphans.
                c = conn.execute(
                    f"DELETE FROM seen_files WHERE {age_clause} AND {still_referenced}",
                    (f"-{days} days", *ref_params),
                )
                res["seen_files"] = c.rowcount

                # 3. Delete records
                c = conn.execute("DELETE FROM records WHERE created_at < datetime('now', ?)", (f"-{days} days",))
                res["records"] = c.rowcount

                # 4. Delete published_artifacts
                c = conn.execute(
                    "DELETE FROM published_artifacts WHERE published_at < datetime('now', ?)", (f"-{days} days",)
                )
                res["published_artifacts"] = c.rowcount

            logger.info(
                f"Database auto-pruned records older than {days} days: "
                f"{res['seen_files']} seen_files, {res['records']} records, "
                f"{res['published_artifacts']} artifacts, {len(res['raw_hashes'])} potential raw blobs."
            )
        except Exception as e:
            logger.error(f"Failed to prune old database records: {e}")
            raise
        return res
