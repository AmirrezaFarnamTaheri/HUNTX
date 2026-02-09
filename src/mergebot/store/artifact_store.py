import hashlib
import logging
import time
from pathlib import Path
from ..utils.atomic import atomic_write
from typing import Optional, List
from .paths import DATA_DIR

logger = logging.getLogger(__name__)


class ArtifactStore:
    def __init__(self, base_dir: Path = DATA_DIR):
        self.base_dir = base_dir
        self.internal_dir = self.base_dir / "dist" / "internal"
        self.output_dir = self.base_dir / "output"
        self.archive_dir = self.base_dir / "archive"

        self.internal_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """
        Saves an internal artifact named by hash.
        Returns the hash of the data.
        """
        h = hashlib.sha256(data).hexdigest()
        target_dir = self.internal_dir / route_name
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{h}.{format_id}"

            atomic_write(target_path, data)

            return h
        except Exception as e:
            logger.error(f"Failed to save internal artifact for '{route_name}': {e}")
            raise

    def get_artifact(self, route_name: str, artifact_hash: str, format_id: str) -> Optional[bytes]:
        path = self.internal_dir / route_name / f"{artifact_hash}.{format_id}"
        if path.exists():
            return path.read_bytes()
        return None

    def save_output(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """
        Saves the user-facing output file (overwriting previous).
        """
        target_path = self.output_dir / f"{route_name}.{format_id}"
        try:
            atomic_write(target_path, data)

            logger.info(f"Saved output artifact: {target_path}")

            # Also save to archive
            self.save_to_archive(route_name, format_id, data)

            return str(target_path)
        except Exception as e:
            logger.error(f"Failed to save output artifact '{target_path.name}': {e}")
            raise

    def save_to_archive(self, route_name: str, format_id: str, data: bytes):
        """
        Saves a copy to the archive directory with a timestamp.
        """
        timestamp = int(time.time())
        filename = f"{route_name}_{timestamp}.{format_id}"
        target_path = self.archive_dir / filename
        try:
            atomic_write(target_path, data)

            logger.info(f"Archived artifact: {target_path}")
        except Exception as e:
            logger.error(f"Failed to archive artifact '{filename}': {e}")

    def prune_archive(self, retention_days: int = 4):
        """
        Removes files from archive older than retention_days.
        """
        now = time.time()
        cutoff = now - (retention_days * 86400)
        count = 0
        try:
            for item in self.archive_dir.iterdir():
                if item.is_file():
                    if item.stat().st_mtime < cutoff:
                        item.unlink()
                        count += 1
            if count > 0:
                logger.info(f"Pruned {count} old files from archive.")
        except Exception as e:
            logger.error(f"Failed to prune archive: {e}")

    def list_archive(self, days: int = 4) -> List[Path]:
        """
        Returns list of files in archive from the last N days.
        """
        now = time.time()
        cutoff = now - (days * 86400)
        files = []
        try:
            for item in self.archive_dir.iterdir():
                if item.is_file() and item.stat().st_mtime >= cutoff:
                    files.append(item)
            # Sort by time desc
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return files
        except Exception as e:
            logger.error(f"Failed to list archive: {e}")
            return []
