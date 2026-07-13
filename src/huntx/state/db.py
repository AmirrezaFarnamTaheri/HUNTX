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
        self.