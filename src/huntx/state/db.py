import contextlib
import logging
import sqlite3
from importlib import resources
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 30_000
_CACHE_SIZE_KIB = 32 * 1024
_MMAP_SIZE_BYTES = 256 * 1024 * 1024


class DBConnection:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            schema = resources.files("huntx.state").joinpath("schema.sql").read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise RuntimeError("Required packaged database schema is missing") from exc

        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA wal_autocheckpoint=1000;")

            try:
                conn.executescript(schema)
            except Exception as exc:
                logger.error("Failed to apply schema: %s", exc)
                raise

            self._check_migrations(conn)
            conn.execute("PRAGMA optimize;")

    def _check_migrations(self, conn: sqlite3.Connection) -> None:
        """Apply incremental schema migrations using ``PRAGMA user_version``."""
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            logger.info("Database schema version: %s", version)

            if version < 1:
                columns = [row["name"] for row in conn.execute("PRAGMA table_info(seen_files)").fetchall()]
                if "metadata_json" not in columns:
                    logger.info("Migrating (v1): Adding metadata_json to seen_files")
                    conn.execute("ALTER TABLE seen_files ADD COLUMN metadata_json TEXT")
                if "filename" not in columns:
                    logger.info("Migrating (v1): Adding filename to seen_files")
                    conn.execute("ALTER TABLE seen_files ADD COLUMN filename TEXT")
                conn.execute("PRAGMA user_version = 1")
                version = 1
                logger.info("Database schema migrated to version 1.")

            if version < 2:
                work_columns = [
                    row["name"] for row in conn.execute("PRAGMA table_info(ingestion_work_items)").fetchall()
                ]
                if work_columns and "rotation_seq" not in work_columns:
                    logger.info("Migrating (v2): Adding rotation_seq to ingestion_work_items")
                    conn.execute(
                        "ALTER TABLE ingestion_work_items " "ADD COLUMN rotation_seq INTEGER NOT NULL DEFAULT 0"
                    )
                conn.execute("PRAGMA user_version = 2")
                version = 2
                logger.info("Database schema migrated to version 2.")

            if version < 3:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_delivery_items (
                        user_id TEXT NOT NULL,
                        artifact_hash TEXT NOT NULL,
                        artifact_name TEXT NOT NULL,
                        delivered_at REAL NOT NULL,
                        PRIMARY KEY (user_id, artifact_hash),
                        FOREIGN KEY (user_id)
                            REFERENCES bot_users(user_id) ON DELETE CASCADE
                    )
                    """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bot_delivery_items_user_time
                    ON bot_delivery_items(user_id, delivered_at DESC)
                    """)
                delivery_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(bot_delivery_items)").fetchall()
                }
                required = {
                    "user_id",
                    "artifact_hash",
                    "artifact_name",
                    "delivered_at",
                }
                if delivery_columns != required:
                    raise RuntimeError(
                        "v3 migration postcondition failed for " f"bot_delivery_items: {sorted(delivery_columns)}"
                    )
                conn.execute("PRAGMA user_version = 3")
                version = 3
                logger.info("Database schema migrated to version 3.")

            if version < 4:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS publication_intents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        publication_key TEXT NOT NULL,
                        artifact_hash TEXT NOT NULL,
                        generation TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        completed_at REAL,
                        UNIQUE(publication_key, artifact_hash, generation),
                        CHECK(length(artifact_hash) = 64)
                    );
                    CREATE TABLE IF NOT EXISTS publication_deliveries (
                        intent_id INTEGER NOT NULL,
                        destination_id TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'desired',
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        last_attempt_at REAL,
                        confirmed_at REAL,
                        remote_receipt TEXT,
                        error_class TEXT,
                        PRIMARY KEY (intent_id, destination_id),
                        FOREIGN KEY (intent_id)
                            REFERENCES publication_intents(id) ON DELETE CASCADE,
                        CHECK(state IN (
                            'desired', 'sending', 'confirmed', 'failed',
                            'unknown_outcome', 'skipped'
                        )),
                        CHECK(attempt_count >= 0)
                    );
                    CREATE INDEX IF NOT EXISTS idx_publication_deliveries_state
                        ON publication_deliveries(state, last_attempt_at);
                    """)
                required_tables = {"publication_intents", "publication_deliveries"}
                existing_tables = {
                    row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                if not required_tables.issubset(existing_tables):
                    raise RuntimeError("v4 publication-ledger migration postcondition failed")
                conn.execute("PRAGMA user_version = 4")
                version = 4
                logger.info("Database schema migrated to version 4.")

            if version < 5:
                record_columns = {row["name"] for row in conn.execute("PRAGMA table_info(records)").fetchall()}
                if "source_observation_id" not in record_columns:
                    conn.execute(
                        "ALTER TABLE records ADD COLUMN source_observation_id INTEGER "
                        "REFERENCES seen_files(id) ON DELETE RESTRICT"
                    )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_records_observation " "ON records(source_observation_id, is_active)"
                )
                migrated_columns = {row["name"] for row in conn.execute("PRAGMA table_info(records)").fetchall()}
                if "source_observation_id" not in migrated_columns:
                    raise RuntimeError("v5 observation-provenance migration postcondition failed")
                conn.execute("PRAGMA user_version = 5")
                version = 5
                logger.info("Database schema migrated to version 5.")

            if version < 6:
                user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bot_users)").fetchall()}
                if "approved" not in user_columns:
                    conn.execute("ALTER TABLE bot_users " "ADD COLUMN approved INTEGER NOT NULL DEFAULT 0")
                conn.execute("PRAGMA user_version = 6")
                version = 6
                logger.info("Database schema migrated to version 6.")

            if version < 7:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS telegram_bot_updates (
                        token_fingerprint TEXT NOT NULL,
                        update_id INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        received_at REAL NOT NULL,
                        PRIMARY KEY (token_fingerprint, update_id),
                        CHECK(length(token_fingerprint) = 64)
                    );
                    CREATE INDEX IF NOT EXISTS idx_telegram_bot_updates_received
                        ON telegram_bot_updates(token_fingerprint, received_at);
                    """)
                inbox_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(telegram_bot_updates)").fetchall()
                }
                required = {
                    "token_fingerprint",
                    "update_id",
                    "payload_json",
                    "received_at",
                }
                if inbox_columns != required:
                    raise RuntimeError("v7 Telegram inbox migration postcondition failed: " f"{sorted(inbox_columns)}")
                conn.execute("PRAGMA user_version = 7")
                version = 7
                logger.info("Database schema migrated to version 7.")

            if version < 8:
                v8_work_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(ingestion_work_items)").fetchall()
                }
                if v8_work_columns and "lease_token" not in v8_work_columns:
                    conn.execute("ALTER TABLE ingestion_work_items ADD COLUMN lease_token TEXT")
                conn.execute("PRAGMA user_version = 8")
                version = 8
                logger.info("Database schema migrated to version 8.")

            if version < 9:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS telegram_bot_consumers (
                        token_fingerprint TEXT NOT NULL,
                        consumer_id TEXT NOT NULL,
                        acknowledged_update_id INTEGER NOT NULL DEFAULT 0,
                        active INTEGER NOT NULL DEFAULT 1,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (token_fingerprint, consumer_id),
                        CHECK(length(token_fingerprint) = 64),
                        CHECK(acknowledged_update_id >= 0),
                        CHECK(active IN (0, 1))
                    );
                    CREATE INDEX IF NOT EXISTS idx_telegram_bot_consumers_watermark
                        ON telegram_bot_consumers(
                            token_fingerprint,
                            active,
                            acknowledged_update_id
                        );
                    """)
                consumer_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(telegram_bot_consumers)").fetchall()
                }
                required = {
                    "token_fingerprint",
                    "consumer_id",
                    "acknowledged_update_id",
                    "active",
                    "updated_at",
                }
                if consumer_columns != required:
                    raise RuntimeError(
                        "v9 Telegram consumer migration postcondition failed: " f"{sorted(consumer_columns)}"
                    )
                conn.execute("PRAGMA user_version = 9")
                version = 9
                logger.info("Database schema migrated to version 9.")
        except Exception as exc:
            logger.error("Migration check failed: %s", exc)
            raise

    @contextlib.contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS};")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute(f"PRAGMA cache_size=-{_CACHE_SIZE_KIB};")
        conn.execute(f"PRAGMA mmap_size={_MMAP_SIZE_BYTES};")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def open_db(path: Path) -> DBConnection:
    return DBConnection(path)
