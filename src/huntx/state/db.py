import contextlib
import logging
import sqlite3
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

        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.warning("schema.sql not found, skipping auto-migration.")
            return

        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA wal_autocheckpoint=1000;")

            try:
                conn.executescript(schema_path.read_text(encoding="utf-8"))
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
                logger.info("Database schema migrated to version 2.")
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
