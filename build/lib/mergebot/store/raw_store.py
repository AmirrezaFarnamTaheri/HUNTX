import hashlib
import logging
from pathlib import Path
from typing import Optional
from .paths import RAW_STORE_DIR

logger = logging.getLogger(__name__)

class RawStore:
    def __init__(self, base_dir: Path = RAW_STORE_DIR):
        self.base_dir = base_dir
        # Ensure base directory exists
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create raw store directory {self.base_dir}: {e}")
            raise

    def save(self, data: bytes) -> str:
        """Saves data to a file named by its SHA256 hash. Returns the hash."""
        try:
            sha256 = hashlib.sha256(data).hexdigest()
            # Sharding by first 2 chars
            prefix = sha256[:2]
            target_dir = self.base_dir / prefix
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / sha256

            # Atomic write if not exists
            if not target_path.exists():
                tmp_path = target_path.with_suffix(".tmp")
                with open(tmp_path, "wb") as f:
                    f.write(data)
                tmp_path.rename(target_path)
                logger.debug(f"Saved new raw blob: {sha256} ({len(data)} bytes)")
            else:
                logger.debug(f"Raw blob {sha256} already exists, skipping write.")

            return sha256
        except Exception as e:
            logger.exception(f"Failed to save raw blob: {e}")
            raise

    def get(self, sha256: str) -> Optional[bytes]:
        """Retrieves data by hash."""
        try:
            prefix = sha256[:2]
            path = self.base_dir / prefix / sha256
            if path.exists():
                data = path.read_bytes()
                # logger.debug(f"Retrieved raw blob: {sha256} ({len(data)} bytes)")
                return data
            logger.warning(f"Raw blob not found: {sha256}")
            return None
        except Exception as e:
            logger.exception(f"Failed to retrieve raw blob {sha256}: {e}")
            return None

    def exists(self, sha256: str) -> bool:
        try:
            prefix = sha256[:2]
            return (self.base_dir / prefix / sha256).exists()
        except Exception:
            return False
