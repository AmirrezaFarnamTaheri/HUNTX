import logging
import json
from typing import Dict, Any, List, Optional, Set
import sqlite3
import time
import uuid

from .proxy_lifecycle import observe_record_identities
from .proxy_retirement import PROXY_UNPUBLISHABLE_SQL

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

    def get_source_states_batch(self, source_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Read all source health cursors with one bounded SQLite connection."""
        if not source_ids:
            return {}
        ids = list(dict.fromkeys(str(item) for item in source_ids))
        collected: Dict[str, Dict[str, Any]] = {}
        with self.db.connect() as conn:
            for start in range(0, len(ids), 400):
                subset = ids[start:start + 400]
                marks = ",".join("?" for _ in subset)
                rows = conn.execute(
                    f"SELECT source_id, state_json FROM source_state "
                    f"WHERE source_id IN ({marks})",
                    subset,
                ).fetchall()
                for row in rows:
                    parsed = json.loads(row["state_json"] or "{}")
                    if not isinstance(parsed, dict):
                        raise ValueError("stored source cursor must be an object")
                    collected[str(row["source_id"])] = parsed
        return collected

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

    def add_record(
        self,
        raw_hash: str,
        record_type: str,
        unique_hash: str,
        data: Dict[str, Any],
        *,
        source_observation_id: int,
    ) -> None:
        if not isinstance(source_observation_id, int) or isinstance(source_observation_id, bool):
            raise ValueError("source_observation_id must be an integer")
        try:
            with self.db.connect() as conn:
                observation = conn.execute(
                    "SELECT raw_hash FROM seen_files WHERE id = ?",
                    (source_observation_id,),
                ).fetchone()
                if observation is None or str(observation["raw_hash"]) != raw_hash:
                    raise ValueError("source_observation_id must identify the supplied raw_hash")
                conn.execute(
                    """
                    INSERT INTO records
                        (source_file_hash, source_observation_id, record_type,
                         unique_hash, data_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        raw_hash,
                        source_observation_id,
                        record_type,
                        unique_hash,
                        json.dumps(data),
                    ),
                )
                observe_record_identities(c=conn, identities=[(record_type, unique_hash)])
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
            identities = [(row[2], row[3]) for row in normalized]
            if conn:
                conn.executemany(sql, normalized)
                observe_record_identities(c=conn, identities=identities)
            else:
                with self.db.connect() as c:
                    c.executemany(sql, normalized)
                    observe_record_identities(c=c, identities=identities)
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

    def schedule_historical_retests(
        self,
        record_types: List[str],
        allowed_source_ids: List[str],
        *,
        min_ingested_at: str,
        limit: int = 64,
    ) -> List[Dict[str, Any]]:
        """Reserve a bounded fair slice of formerly authenticated proxies.

        The normal source-window query is unchanged. These rows are only
        *candidates* for an entirely new HTTPS check, never working proxies.
        Selection is persisted atomically across runs so a retained historical
        identity cannot be perpetually hidden behind earlier source records.
        Only approved observation provenance, active records, genuine past
        authenticated success and nonterminal lifecycle states qualify.
        """
        import hashlib
        from datetime import datetime
        from ..formats.npvt import canonical_proxy_identity
        from ..formats.proxy_uri_validator import validate_proxy_uri

        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("historical retest limit must be an integer from 1 to 256")
        types = list(dict.fromkeys(record_types))
        if any(kind not in ("npvt", "npvtsub") for kind in types):
            raise ValueError("historical retesting is only for canonical proxy formats")
        sources = list(dict.fromkeys(allowed_source_ids))
        if not types or not sources:
            return []
        if any(not isinstance(source, str) or not source for source in sources):
            raise ValueError("historical retests require approved source IDs")
        if not isinstance(min_ingested_at, str):
            raise ValueError("historical retests require an ingestion cutoff")
        try:
            datetime.strptime(min_ingested_at, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError("invalid historical retest ingestion cutoff") from exc

        type_slots = ",".join("?" for _ in types)
        source_slots = ",".join("?" for _ in sources)
        # A valid fresh observation is already in get_records_for_build().
        # Only add old candidates, or suppressed recent candidates that the
        # normal query excludes. Suppressed does not mean permanently dead.
        query = f"""
            WITH eligible AS (
                SELECT r.record_type, r.unique_hash, MAX(r.id) AS record_id
                FROM records AS r
                JOIN seen_files AS s ON s.id = r.source_observation_id
                JOIN proxy_lifecycle AS l
                  ON l.record_type = r.record_type AND l.unique_hash = r.unique_hash
                WHERE r.record_type IN ({type_slots})
                  AND s.source_id IN ({source_slots})
                  AND r.is_active = 1
                  AND l.authenticated_successes > 0
                  AND l.last_success_at IS NOT NULL
                  AND l.lifecycle_status NOT IN ('dead', 'revoked', 'archived')
                  AND (s.ingested_at < ? OR l.lifecycle_status = 'suspect')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM records AS recent
                      JOIN seen_files AS fresh
                        ON fresh.id = recent.source_observation_id
                      WHERE recent.record_type = r.record_type
                        AND recent.unique_hash = r.unique_hash
                        AND recent.is_active = 1
                        AND fresh.source_id IN ({source_slots})
                        AND fresh.ingested_at >= ?
                        AND NOT EXISTS (
                            SELECT 1 FROM proxy_lifecycle AS p
                            WHERE p.unique_hash = recent.unique_hash
                              AND p.record_type = recent.record_type
                              AND ({PROXY_UNPUBLISHABLE_SQL})
                        )
                  )
                GROUP BY r.record_type, r.unique_hash
            )
            SELECT r.record_type, r.unique_hash, r.data_json
            FROM eligible AS e
            JOIN records AS r ON r.id = e.record_id
            LEFT JOIN proxy_retest_schedule AS q
              ON q.record_type = r.record_type AND q.unique_hash = r.unique_hash
            JOIN proxy_lifecycle AS l
              ON l.record_type = r.record_type AND l.unique_hash = r.unique_hash
            ORDER BY COALESCE(q.selection_count, 0),
                     COALESCE(q.last_selected_at, 0),
                     COALESCE(l.last_probe_at, 0), r.id
            LIMIT ?
        """
        args: List[Any] = [
            *types, *sources, min_ingested_at,
            *sources, min_ingested_at, limit,
        ]
        with self.db.connect() as conn:
            # BEGIN IMMEDIATE serializes concurrent route selectors. Reserve
            # only after validating *every* selected URI; on failure the
            # connection rolls back and no position is silently consumed.
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(query, args).fetchall()
            candidates: List[Dict[str, Any]] = []
            for row in rows:
                data = json.loads(row["data_json"])
                line = data.get("line") if isinstance(data, dict) else None
                if not isinstance(line, str) or not validate_proxy_uri(line):
                    raise ValueError("historical proxy retest has invalid record data")
                digest = hashlib.sha256(
                    canonical_proxy_identity(line).encode("utf-8")
                ).hexdigest()
                if digest != row["unique_hash"]:
                    raise ValueError("historical proxy retest has mismatched identity")
                candidates.append({
                    "record_type": row["record_type"],
                    "data": data,
                    "historical_retest": True,
                })
            if rows:
                clock = time.time()
                conn.executemany(
                    """
                    INSERT INTO proxy_retest_schedule(
                        record_type, unique_hash, last_selected_at, selection_count
                    ) VALUES (?, ?, ?, 1)
                    ON CONFLICT(record_type, unique_hash) DO UPDATE SET
                        last_selected_at = excluded.last_selected_at,
                        selection_count = proxy_retest_schedule.selection_count + 1
                    """,
                    [
                        (row["record_type"], row["unique_hash"], clock)
                        for row in rows
                    ],
                )
        return candidates

    def get_records_for_build(
        self,
        record_types: List[str],
        allowed_source_ids: List[str],
        min_seen_file_id: Optional[int] = None,
        min_ingested_at: Optional[str] = None,
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
            if min_ingested_at is not None:
                where_extra += " AND s.ingested_at >= ?"
                args.append(min_ingested_at)

            # source_observation_id binds each normalized record to the exact
            # seen_files observation whose source identity authorized it.
            query = f"""
                WITH filtered AS (
                    SELECT DISTINCT r.id, r.record_type, r.unique_hash, r.data_json
                    FROM records r
                    JOIN seen_files s ON r.source_observation_id = s.id
                    WHERE r.record_type IN ({placeholders_types})
                      AND s.source_id IN ({placeholders_sources})
                      AND r.is_active = 1
                      AND NOT EXISTS (
                          SELECT 1 FROM proxy_lifecycle p
                          WHERE p.unique_hash = r.unique_hash
                            AND p.record_type = r.record_type
                            AND {PROXY_UNPUBLISHABLE_SQL}
                      )
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
                    SELECT ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM published_artifacts
                        WHERE route_name = ? AND artifact_hash = ?
                    )
                    """,
                    (route_name, artifact_hash, metadata_json, route_name, artifact_hash),
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

    def mark_delivery_sending(
        self, intent_id: int, destination_id: str, *, attempt_token: str | None = None
    ) -> bool:
        """Atomically claim a pending or definitively failed delivery.

        A sending, confirmed, or unknown-outcome delivery cannot be stolen.
        The token fences completions from obsolete attempts after reconciliation.
        """
        attempt_token = attempt_token or uuid.uuid4().hex
        with self.db.connect() as conn:
            result = conn.execute(
                """
                INSERT INTO publication_deliveries
                    (intent_id, destination_id, state, attempt_count,
                     last_attempt_at, attempt_token)
                VALUES (?, ?, 'sending', 1, ?, ?)
                ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                    state='sending',
                    attempt_count=publication_deliveries.attempt_count + 1,
                    last_attempt_at=excluded.last_attempt_at,
                    attempt_token=excluded.attempt_token,
                    error_class=NULL
                WHERE publication_deliveries.state IN ('desired', 'failed')
                """,
                (intent_id, destination_id, time.time(), attempt_token),
            )
            return result.rowcount == 1

    def mark_delivery_confirmed(
        self, intent_id: int, destination_id: str, *,
        remote_receipt: Optional[str] = None, attempt_token: Optional[str] = None,
    ) -> None:
        """Confirm an owned attempt without letting a stale worker overwrite it."""
        now = time.time()
        with self.db.connect() as conn:
            if attempt_token is None:
                # Legacy seeding and explicit out-of-band confirmation callers.
                conn.execute(
                    """
                    INSERT INTO publication_deliveries
                        (intent_id, destination_id, state, attempt_count,
                         last_attempt_at, confirmed_at, remote_receipt)
                    VALUES (?, ?, 'confirmed', 1, ?, ?, ?)
                    ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                        state='confirmed', confirmed_at=excluded.confirmed_at,
                        remote_receipt=COALESCE(excluded.remote_receipt, publication_deliveries.remote_receipt),
                        error_class=NULL
                    """,
                    (intent_id, destination_id, now, now, remote_receipt),
                )
            else:
                updated = conn.execute(
                    """
                    UPDATE publication_deliveries SET
                        state='confirmed', confirmed_at=?, remote_receipt=?, error_class=NULL
                    WHERE intent_id=? AND destination_id=?
                      AND state='sending' AND attempt_token=?
                    """,
                    (now, remote_receipt, intent_id, destination_id, attempt_token),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("Lost publication delivery claim before confirmation")

    def mark_delivery_failed(
        self, intent_id: int, destination_id: str, *,
        error_class: str, unknown_outcome: bool = False,
        attempt_token: Optional[str] = None,
    ) -> None:
        """Record a definite or ambiguous failure without crossing claim owners."""
        state = "unknown_outcome" if unknown_outcome else "failed"
        with self.db.connect() as conn:
            if attempt_token is None:
                conn.execute(
                    """
                    INSERT INTO publication_deliveries
                        (intent_id, destination_id, state, attempt_count,
                         last_attempt_at, error_class)
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(intent_id, destination_id) DO UPDATE SET
                        state=excluded.state, last_attempt_at=excluded.last_attempt_at,
                        error_class=excluded.error_class
                    WHERE publication_deliveries.state != 'confirmed'
                    """,
                    (intent_id, destination_id, state, time.time(), error_class),
                )
            else:
                updated = conn.execute(
                    """
                    UPDATE publication_deliveries SET
                        state=?, last_attempt_at=?, error_class=?
                    WHERE intent_id=? AND destination_id=?
                      AND state='sending' AND attempt_token=?
                    """,
                    (state, time.time(), error_class, intent_id, destination_id, attempt_token),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("Lost publication delivery claim before failure record")

    def reconcile_delivery(
        self, intent_id: int, destination_id: str, *, outcome: str,
        operator: str, reason: str, remote_receipt: Optional[str] = None,
        min_sending_age_seconds: float = 120.0,
    ) -> None:
        """Audit an operator-verified remote result; never infer it from time.

        Confirmed outcomes require a remote receipt. A not-delivered outcome
        requires independent evidence that no document was accepted.
        """
        if outcome not in {"confirmed", "not_delivered"}:
            raise ValueError("outcome must be confirmed or not_delivered")
        if not operator.strip() or not reason.strip():
            raise ValueError("operator and supporting reason are required")
        if outcome == "confirmed" and not (remote_receipt or "").strip():
            raise ValueError("verified remote receipt required for confirmation")
        if outcome == "not_delivered" and remote_receipt:
            raise ValueError("not_delivered cannot carry a confirmed receipt")
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT state, last_attempt_at FROM publication_deliveries
                WHERE intent_id=? AND destination_id=?
                """, (intent_id, destination_id),
            ).fetchone()
            if row is None or row["state"] not in {"sending", "unknown_outcome"}:
                raise ValueError("delivery is not in a reconcilable state")
            now = time.time()
            if row["state"] == "sending" and (
                row["last_attempt_at"] is None
                or now - float(row["last_attempt_at"]) < max(0.0, min_sending_age_seconds)
            ):
                raise ValueError("sending delivery may still have an active worker")
            state = "confirmed" if outcome == "confirmed" else "failed"
            changed = conn.execute(
                """
                UPDATE publication_deliveries SET state=?, confirmed_at=?,
                    remote_receipt=?, error_class=?, attempt_token=NULL
                WHERE intent_id=? AND destination_id=? AND state=?
                """, (
                    state, now if state == "confirmed" else None,
                    remote_receipt, None if state == "confirmed" else "ReconciledNotDelivered",
                    intent_id, destination_id, row["state"],
                ),
            )
            if changed.rowcount != 1:
                raise RuntimeError("delivery changed during reconciliation")
            conn.execute(
                """
                INSERT INTO publication_delivery_reconciliations
                    (intent_id, destination_id, previous_state, resulting_state,
                     operator, reason, remote_receipt, reconciled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id, destination_id, row["state"], state,
                    operator.strip(), reason.strip(), remote_receipt, now,
                ),
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
                          AND NOT EXISTS (
                              SELECT 1 FROM seen_files pending
                              WHERE pending.raw_hash = sf.raw_hash
                                AND pending.status = 'pending'
                          )
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
                    cursor = conn.execute("""
                        SELECT DISTINCT sf.raw_hash FROM seen_files sf
                        WHERE sf.status != 'pending'
                          AND NOT EXISTS (
                              SELECT 1 FROM seen_files pending
                              WHERE pending.raw_hash = sf.raw_hash
                                AND pending.status = 'pending'
                          )
                        """)
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

    def persist_authenticated_build_evidence(
        self, record_type: str, artifact_bytes: bytes, evidence_bytes: bytes,
    ) -> int:
        """Persist only real, identity-matched authenticated build successes.

        The sidecar contains no proxy credentials. A successful historical
        observation authorizes *retention for future retesting*, not a fresh
        publication claim after its five-minute expiry. Only the producer
        HTTPS gate can create the sidecar; never persist TCP-only estimates.
        """
        import hashlib
        import math

        from ..formats.npvt import canonical_proxy_identity
        from .proxy_lifecycle import record_authenticated_probe

        if record_type not in {"npvt", "npvtsub"}:
            raise ValueError("only canonical proxy feeds have authenticated sidecars")
        try:
            report = json.loads(evidence_bytes)
            lines = [
                line.strip() for line in artifact_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
        except (ValueError, UnicodeError, TypeError) as exc:
            raise ValueError("invalid producer authenticated sidecar") from exc
        if not isinstance(report, dict):
            raise ValueError("invalid producer authenticated sidecar")
        observations = report.get("records")
        if (
            report.get("schema_version") != 1
            or report.get("evidence") != "publisher_authenticated_https"
            or type(report.get("admitted_count")) is not int
            or not isinstance(observations, dict)
            or report["admitted_count"] != len(lines)
            or len(observations) != len(lines)
        ):
            raise ValueError("producer authenticated sidecar count mismatch")
        digests = [
            hashlib.sha256(canonical_proxy_identity(line).encode("utf-8")).hexdigest()
            for line in lines
        ]
        if len(set(digests)) != len(lines) or set(observations) != set(digests):
            raise ValueError("producer authenticated sidecar identity mismatch")

        verified: list[tuple[str, int, float]] = []
        for digest in sorted(observations):
            entry = observations[digest]
            if not isinstance(entry, dict):
                raise ValueError("invalid producer authenticated sidecar measurement")
            checked, expires, duration = (
                entry.get("checked_at"), entry.get("expires_at"),
                entry.get("duration_ms"),
            )
            if (
                not isinstance(checked, (int, float)) or isinstance(checked, bool)
                or not isinstance(expires, (int, float)) or isinstance(expires, bool)
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)
            ):
                raise ValueError("invalid producer authenticated sidecar measurement")
            checked_at = float(checked)
            expires_at = float(expires)
            duration_ms = float(duration)
            if (
                not all(math.isfinite(value)
                        for value in (checked_at, expires_at, duration_ms))
                or checked_at <= 0
                or not 0 < expires_at - checked_at <= 300.001
                or not 0 <= duration_ms <= 30000
            ):
                raise ValueError("invalid producer authenticated sidecar measurement")
            verified.append((digest, int(checked_at), duration_ms))

        persisted = 0
        for digest, checked, duration in verified:
            # The existing probe ledger enforces idempotence, terminal
            # revocation and monotonic evidence per identity.
            inserted = record_authenticated_probe(
                self.db,
                unique_hash=digest,
                record_type=record_type,
                probe_id=f"build:{record_type}:{digest}:{checked * 1000}",
                vantage_id="producer-isolated-https",
                success=True,
                latency_ms=duration,
                checked_at=checked,
            )
            persisted += int(inserted)
        return persisted

    def persist_expired_authenticated_gate_evidence(
        self, record_type: str, candidates: list[Any], report: dict[str, Any],
    ) -> int:
        """Keep earlier real HTTPS success for retesting, never publication.

        Validate every canonical candidate digest against the completed gate
        first. Only status 'success_expired_before_publication' qualifies:
        budget exhaustion, a refused connection or a TCP-only observation
        cannot create a working-history receipt. Keep all secrets out of the
        evidence ledger; monotonic probe ordering blocks stale resurrection.
        """
        import hashlib
        import math

        from ..formats.npvt import canonical_proxy_identity
        from .proxy_lifecycle import record_authenticated_probe

        if record_type not in {"npvt", "npvtsub"} or not isinstance(report, dict):
            raise ValueError("invalid authenticated history gate")
        if (
            report.get("schema_version") != 1
            or report.get("scope") != "single_authenticated_https_sweep"
        ):
            raise ValueError("invalid authenticated history gate schema")
        dispositions = report.get("identities")
        history = report.get("historical_authenticated_successes", {})
        if not isinstance(dispositions, dict) or not isinstance(history, dict):
            raise ValueError("invalid authenticated history evidence")

        observed: set[str] = set()
        for item in candidates:
            fields = item.get("data", item) if isinstance(item, dict) else item
            line = fields.get("line") if isinstance(fields, dict) else fields
            if not isinstance(line, str) or not line.strip():
                raise ValueError("invalid authenticated history candidate")
            digest = hashlib.sha256(
                canonical_proxy_identity(line).encode("utf-8")
            ).hexdigest()
            observed.add(digest)
        if (
            not observed
            or set(dispositions) != observed
            or type(report.get("candidates")) is not int
            or report["candidates"] != len(observed)
            or type(report.get("admitted")) is not int
            or type(report.get("rejected")) is not int
            or report["admitted"] + report["rejected"] != len(observed)
        ):
            raise ValueError("authenticated history candidate identity mismatch")
        if any(
            not isinstance(value, str) for value in dispositions.values()
        ):
            raise ValueError("invalid authenticated history dispositions")
        for digest in history:
            if dispositions.get(digest) != "success_expired_before_publication":
                raise ValueError("expired HTTPS proof identity/status mismatch")

        now = time.time()
        validated: list[tuple[str, int, float]] = []
        for digest in sorted(history):
            details = history[digest]
            if not isinstance(details, dict) or set(details) != {
                "checked_at", "expires_at", "duration_ms",
            }:
                raise ValueError("invalid historical authenticated proof")
            checked = details["checked_at"]
            expires = details["expires_at"]
            duration = details["duration_ms"]
            if any(
                type(value) not in (int, float) or not math.isfinite(value)
                for value in (checked, expires, duration)
            ):
                raise ValueError("invalid historical authenticated proof measurements")
            if (
                not 0 < checked < expires <= now
                or not 0 < expires - checked <= 300.001
                or now - checked > 10800
                or not 0 <= duration <= 30000
            ):
                raise ValueError("invalid historical authenticated proof window")
            validated.append((digest, int(checked), float(duration)))

        added = 0
        for digest, checked, latency_ms in validated:
            with self.db.connect() as conn:
                lifecycle = conn.execute(
                    "SELECT lifecycle_status, last_probe_at FROM proxy_lifecycle "
                    "WHERE unique_hash = ? AND record_type = ?",
                    (digest, record_type),
                ).fetchone()
            if lifecycle is not None and (
                lifecycle["lifecycle_status"] in ("dead", "revoked", "archived")
                or (
                    lifecycle["last_probe_at"] is not None
                    and int(lifecycle["last_probe_at"]) > checked
                )
            ):
                # Preserve terminal policy and newer negative observations.
                continue
            inserted = record_authenticated_probe(
                self.db, unique_hash=digest, record_type=record_type,
                probe_id=f"expired-build:{record_type}:{digest}:{checked * 1000}",
                vantage_id="producer-isolated-https", success=True,
                latency_ms=latency_ms, checked_at=checked,
            )
            added += int(inserted)
        return added

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

                # Remove expired children before their observations: the exact
                # provenance foreign key deliberately uses ON DELETE RESTRICT.
                # Keep every historically authenticated proxy available for
                # deliberate future rechecks, even when the discovery source
                # has not refreshed in the normal retention window. A failed
                # probe or a slower connection is NOT proof of permanent death.
                # Explicit revocation/death/archival remains authoritative.
                # This does not make an old record publication-eligible: the
                # current build window and per-node fresh HTTPS gate still
                # require independent recent authentication.
                c = conn.execute(
                    """
                    DELETE FROM records
                    WHERE created_at < datetime('now', ?)
                      AND NOT EXISTS (
                          SELECT 1 FROM proxy_lifecycle p
                          WHERE p.unique_hash = records.unique_hash
                            AND p.record_type = records.record_type
                            AND p.last_success_at IS NOT NULL
                            AND p.authenticated_successes > 0
                            AND p.lifecycle_status NOT IN ('dead', 'revoked', 'archived')
                      )
                    """,
                    (f"-{days} days",),
                )
                res["records"] = c.rowcount

                # A fresh record still needs its observation, even when its raw
                # bytes are not required by the format at build time.
                age_clause = (
                    "ingested_at < datetime('now', ?) AND status != 'pending' "
                    "AND NOT EXISTS (SELECT 1 FROM records r "
                    "WHERE r.source_observation_id = seen_files.id)"
                )

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

                # 3. Delete published_artifacts
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
