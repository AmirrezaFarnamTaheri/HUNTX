import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


class DBConnection:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.warning("schema.sql not found, skipping auto-migration.")
            return

        with self.connect() as conn:
            # Enable WAL for better read/write concurrency.
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            try:
                with open(schema_path, "r", encoding="utf-8") as schema_file:
                    conn.executescript(schema_file.read())
            except Exception as exc:
                logger.error("Failed to apply schema: %s", exc)
                raise

            self._check_migrations(conn)

    def _check_migrations(self, conn: sqlite3.Connection):
        """Apply incremental schema migrations using ``PRAGMA user_version``."""
        try:
            cursor = conn.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            logger.info("Database schema version: %s", version)

            if version < 1:
                cursor = conn.execute("PRAGMA table_info(seen_files)")
                columns = [row["name"] for row in cursor.fetchall()]
                if "metadata_json" not in columns:
                    logger.info("Migrating (v1): Adding metadata_json to seen_files")
                    conn.execute("ALTER TABLE seen_files ADD COLUMN metadata_json TEXT")
                if "filename" not in columns:
                    logger.info("Migrating (v1): Adding filename to seen_files")
                    conn.execute("ALTER TABLE seen_files ADD COLUMN filename TEXT")
                conn.execute("PRAGMA user_version = 1")
                logger.info("Database schema migrated to version 1.")
        except Exception as exc:
            logger.error("Migration check failed: %s", exc)
            raise

    @contextlib.contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        # The sqlite timeout is a connection-open setting. ``busy_timeout`` is
        # also applied explicitly because every worker opens independent
        # short-lived connections.
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
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
