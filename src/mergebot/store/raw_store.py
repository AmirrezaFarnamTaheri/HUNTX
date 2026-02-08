import hashlib
import logging
from pathlib import Path
from typing import Optional
from ..utils.atomic import atomic_write
from .paths import RAW_STORE_DIR

logger = logging.getLogger(__name__)


class RawStore:
    def __init__(self, base_dir: Path = RAW_STORE_DIR):
        self.base_dir = base_dir
        self._ensured_dirs = set()
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

            if target_dir not in self._ensured_dirs:
                target_dir.mkdir(parents=True, exist_ok=True)
                self._ensured_dirs.add(target_dir)

            target_path = target_dir / sha256

            # Atomic write if not exists
            if not target_path.exists():
                atomic_write(target_path, data)
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

    def prune_processed(self, state_repo) -> int:
        """Remove raw blobs whose files have already been processed or failed."""
        pruned = 0
        try:
            processed_hashes = state_repo.get_processed_hashes()
            for h in processed_hashes:
                prefix = h[:2]
                path = self.base_dir / prefix / h
                if path.exists():
                    path.unlink()
                    pruned += 1
            if pruned:
                logger.info(f"Pruned {pruned} processed raw blobs.")
            # Remove empty shard directories
            for d in self.base_dir.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
        except Exception as e:
            logger.error(f"Failed to prune raw store: {e}")
        return pruned
