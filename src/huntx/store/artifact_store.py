import hashlib
import logging
import time
from pathlib import Path
from ..utils.atomic import atomic_write
from ..utils.safe_names import safe_component
from typing import Optional, List
from . import paths

logger = logging.getLogger(__name__)


class ArtifactStore:
    def __init__(self, base_dir: Optional[Path] = None):
        # IMPORTANT: compute default at runtime (after paths.set_paths()).
        self.base_dir = base_dir or paths.DATA_DIR
        self.internal_dir = self.base_dir / "dist" / "internal"
        self.output_dir = self.base_dir / "outputs"
        self.archive_dir = self.base_dir / "archive"

        self.internal_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """
        Saves an internal artifact named by hash.
        Returns the hash of the data.
        """
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        h = hashlib.sha256(data).hexdigest()
        
        # Robust path traversal validation
        try:
            target_dir = (self.internal_dir / safe_route).resolve()
            if not target_dir.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in route name: {route_name}")
            
            target_path = (target_dir / f"{h}.{safe_fmt}").resolve()
            if not target_path.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in format ID: {format_id}")
        except Exception as e:
            logger.error(f"Path validation failed in save_artifact for '{route_name}': {e}")
            raise ValueError(f"Invalid path or path traversal: {e}")

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(target_path, data)
            return h
        except Exception as e:
            logger.error(f"Failed to save internal artifact for '{safe_route}': {e}")
            raise

    def get_artifact(self, route_name: str, artifact_hash: str, format_id: str) -> Optional[bytes]:
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")
        
        try:
            path = (self.internal_dir / safe_route / f"{artifact_hash}.{safe_fmt}").resolve()
            if not path.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in get_artifact: {route_name}")
        except Exception as e:
            logger.error(f"Path validation failed in get_artifact: {e}")
            return None

        if path.exists():
            return path.read_bytes()
        return None

    def save_output(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """
        Saves the user-facing output file (overwriting previous).
        """
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        try:
            target_path = (self.output_dir / f"{safe_route}.{safe_fmt}").resolve()
            if not target_path.is_relative_to(self.output_dir.resolve()):
                raise ValueError(f"Path traversal detected in save_output: {route_name}")
        except Exception as e:
            logger.error(f"Path validation failed in save_output for '{route_name}.{format_id}': {e}")
            raise ValueError(f"Invalid path or path traversal: {e}")

        try:
            atomic_write(target_path, data)
            logger.info(f"Saved output artifact: {target_path}")

            # Also save to archive
            self.save_to_archive(safe_route, safe_fmt, data)
            return str(target_path)
        except Exception as e:
            logger.error(f"Failed to save output artifact '{target_path.name}': {e}")
            raise

    def save_to_archive(self, route_name: str, format_id: str, data: bytes):
        """
        Saves a copy to the archive directory with a timestamp.
        """
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        timestamp = int(time.time())
        filename = f"{safe_route}_{timestamp}.{safe_fmt}"
        
        try:
            target_path = (self.archive_dir / filename).resolve()
            if not target_path.is_relative_to(self.archive_dir.resolve()):
                raise ValueError(f"Path traversal detected in save_to_archive: {filename}")
        except Exception as e:
            logger.error(f"Path validation failed in save_to_archive: {e}")
            raise ValueError(f"Invalid path or path traversal: {e}")

        try:
            atomic_write(target_path, data)
            logger.info(f"Archived artifact: {target_path}")
        except Exception as e:
            logger.error(f"Failed to archive artifact '{filename}': {e}")
            raise

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
