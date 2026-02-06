import sqlite3
import contextlib
import logging
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
            # Enable WAL
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            # Run basic schema
            try:
                with open(schema_path, "r") as f:
                    conn.executescript(f.read())
            except Exception as e:
                logger.error(f"Failed to apply schema: {e}")
                raise

            # Check for migrations
            self._check_migrations(conn)

    def _check_migrations(self, conn: sqlite3.Connection):
        """
        Manually handle schema migrations that aren't covered by IF NOT EXISTS
        """
        # Check if metadata_json column exists in seen_files
        try:
            cursor = conn.execute("PRAGMA table_info(seen_files)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "metadata_json" not in columns:
                logger.info("Migrating: Adding metadata_json to seen_files")
                conn.execute("ALTER TABLE seen_files ADD COLUMN metadata_json TEXT")
        except Exception as e:
            logger.error(f"Migration check failed: {e}")


    @contextlib.contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
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
