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

            # Run migration
            try:
                with open(schema_path, "r") as f:
                    conn.executescript(f.read())
            except Exception as e:
                logger.error(f"Failed to apply schema: {e}")
                raise

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
