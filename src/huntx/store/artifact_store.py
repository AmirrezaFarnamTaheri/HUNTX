import hashlib
import logging
import time
from pathlib import Path
from typing import List, Optional

from ..utils.atomic import atomic_write, atomic_write_if_changed
from ..utils.safe_names import safe_component
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
        """Save immutable content-addressed artifact data and return its hash."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")
        artifact_hash = hashlib.sha256(data).hexdigest()

        try:
            target_dir = (self.internal_dir / safe_route).resolve()
            if not target_dir.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in route name: {route_name}")
            target_path = (target_dir / f"{artifact_hash}.{safe_fmt}").resolve()
            if not target_path.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in format ID: {format_id}")
        except Exception as exc:
            logger.error("Path validation failed in save_artifact for %r: %s", route_name, exc)
            raise ValueError(f"Invalid path or path traversal: {exc}") from exc

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            if not target_path.exists():
                atomic_write(target_path, data)
            return artifact_hash
        except Exception as exc:
            logger.error("Failed to save internal artifact for %r: %s", safe_route, exc)
            raise

    def get_artifact(self, route_name: str, artifact_hash: str, format_id: str) -> Optional[bytes]:
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        try:
            path = (self.internal_dir / safe_route / f"{artifact_hash}.{safe_fmt}").resolve()
            if not path.is_relative_to(self.internal_dir.resolve()):
                raise ValueError(f"Path traversal detected in get_artifact: {route_name}")
        except Exception as exc:
            logger.error("Path validation failed in get_artifact: %s", exc)
            return None

        return path.read_bytes() if path.exists() else None

    def save_output(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """Save a user-facing output, archiving it only when content changed."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        try:
            target_path = (self.output_dir / f"{safe_route}.{safe_fmt}").resolve()
            if not target_path.is_relative_to(self.output_dir.resolve()):
                raise ValueError(f"Path traversal detected in save_output: {route_name}")
        except Exception as exc:
            logger.error("Path validation failed in save_output for %r.%r: %s", route_name, format_id, exc)
            raise ValueError(f"Invalid path or path traversal: {exc}") from exc

        try:
            changed = atomic_write_if_changed(target_path, data)
            if changed:
                logger.info("Saved changed output artifact: %s", target_path)
                self.save_to_archive(safe_route, safe_fmt, data)
            else:
                logger.debug("Output artifact unchanged; skipped write/archive: %s", target_path)
            return str(target_path)
        except Exception as exc:
            logger.error("Failed to save output artifact %r: %s", target_path.name, exc)
            raise

    def save_to_archive(self, route_name: str, format_id: str, data: bytes) -> None:
        """Save a timestamped archive copy for changed output content."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")
        timestamp = time.time_ns()
        filename = f"{safe_route}_{timestamp}.{safe_fmt}"

        try:
            target_path = (self.archive_dir / filename).resolve()
            if not target_path.is_relative_to(self.archive_dir.resolve()):
                raise ValueError(f"Path traversal detected in save_to_archive: {filename}")
        except Exception as exc:
            logger.error("Path validation failed in save_to_archive: %s", exc)
            raise ValueError(f"Invalid path or path traversal: {exc}") from exc

        try:
            atomic_write(target_path, data)
            logger.info("Archived changed artifact: %s", target_path)
        except Exception as exc:
            logger.error("Failed to archive artifact %r: %s", filename, exc)
            raise

    def prune_archive(self, retention_days: int = 4) -> None:
        """Remove archive files older than ``retention_days``."""
        cutoff = time.time() - (retention_days * 86400)
        count = 0
        try:
            for item in self.archive_dir.iterdir():
                if item.is_file() and item.stat().st_mtime < cutoff:
                    item.unlink()
                    count += 1
            if count:
                logger.info("Pruned %s old files from archive.", count)
        except Exception as exc:
            logger.error("Failed to prune archive: %s", exc)

    def list_archive(self, days: int = 4) -> List[Path]:
        """Return archive files from the last ``days`` days, newest first."""
        cutoff = time.time() - (days * 86400)
        try:
            files = [item for item in self.archive_dir.iterdir() if item.is_file() and item.stat().st_mtime >= cutoff]
            files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            return files
        except Exception as exc:
            logger.error("Failed to list archive: %s", exc)
            return []
