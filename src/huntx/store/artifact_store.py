import hashlib
import logging
import time
from pathlib import Path
from typing import List, Optional

from ..utils.atomic import atomic_write_if_changed
from ..utils.safe_names import safe_component
from . import paths

logger = logging.getLogger(__name__)


class ArtifactStore:
    def __init__(self, base_dir: Optional[Path] = None):
        # Compute defaults at runtime, after paths.set_paths() may have run.
        self.base_dir = base_dir or paths.DATA_DIR
        self.internal_dir = self.base_dir / "dist" / "internal"
        self.output_dir = self.base_dir / "outputs"
        self.archive_dir = self.base_dir / "archive"

        for directory in (self.internal_dir, self.output_dir, self.archive_dir):
            directory.mkdir(parents=True, exist_ok=True)

        # Resolving roots once avoids repeated filesystem work on every artifact.
        self._internal_root = self.internal_dir.resolve()
        self._output_root = self.output_dir.resolve()
        self._archive_root = self.archive_dir.resolve()

    @staticmethod
    def _validated_child(root: Path, child: Path, label: str) -> Path:
        target = child.resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Path traversal detected in {label}: {target}")
        return target

    def save_artifact(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """Save an internal content-addressed artifact and return its SHA-256."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")
        artifact_hash = hashlib.sha256(data).hexdigest()

        try:
            target_dir = self._validated_child(
                self._internal_root,
                self.internal_dir / safe_route,
                "route name",
            )
            target_path = self._validated_child(
                self._internal_root,
                target_dir / f"{artifact_hash}.{safe_fmt}",
                "format ID",
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_if_changed(target_path, data)
            return artifact_hash
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to save internal artifact for %r: %s", safe_route, exc)
            raise

    def get_artifact(self, route_name: str, artifact_hash: str, format_id: str) -> Optional[bytes]:
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        try:
            path = self._validated_child(
                self._internal_root,
                self.internal_dir / safe_route / f"{artifact_hash}.{safe_fmt}",
                "artifact lookup",
            )
        except ValueError as exc:
            logger.error("Path validation failed in get_artifact: %s", exc)
            return None

        return path.read_bytes() if path.exists() else None

    def save_output(self, route_name: str, format_id: str, data: bytes) -> Optional[str]:
        """Save a user-facing output, archiving only when its content changed."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")

        target_path = self.output_dir / f"{safe_route}.{safe_fmt}"
        try:
            target_path = self._validated_child(
                self._output_root,
                target_path,
                "output",
            )
            changed = atomic_write_if_changed(target_path, data)
            if changed:
                logger.info("Saved changed output artifact: %s", target_path)
                self.save_to_archive(safe_route, safe_fmt, data)
            else:
                logger.debug("Output artifact unchanged, skipped write/archive: %s", target_path)
            return str(target_path)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to save output artifact %r: %s", target_path.name, exc)
            raise

    def save_to_archive(self, route_name: str, format_id: str, data: bytes) -> None:
        """Save a changed output to a collision-resistant timestamped archive."""
        safe_route = safe_component(route_name, default="route")
        safe_fmt = safe_component(format_id, default="fmt")
        filename = f"{safe_route}_{time.time_ns()}.{safe_fmt}"

        try:
            target_path = self._validated_child(
                self._archive_root,
                self.archive_dir / filename,
                "archive",
            )
            atomic_write_if_changed(target_path, data)
            logger.info("Archived artifact: %s", target_path)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to archive artifact %r: %s", filename, exc)
            raise

    def prune_archive(self, retention_days: int = 4) -> None:
        """Remove archive files older than retention_days."""
        cutoff = time.time() - (retention_days * 86400)
        count = 0
        try:
            for item in self.archive_dir.iterdir():
                try:
                    if item.is_file() and item.stat().st_mtime < cutoff:
                        item.unlink()
                        count += 1
                except FileNotFoundError:
                    continue
            if count:
                logger.info("Pruned %s old files from archive.", count)
        except Exception as exc:
            logger.error("Failed to prune archive: %s", exc)

    def list_archive(self, days: int = 4) -> List[Path]:
        """Return archive files from the last N days, newest first."""
        cutoff = time.time() - (days * 86400)
        entries: list[tuple[float, Path]] = []
        try:
            for item in self.archive_dir.iterdir():
                try:
                    if not item.is_file():
                        continue
                    modified = item.stat().st_mtime
                    if modified >= cutoff:
                        entries.append((modified, item))
                except FileNotFoundError:
                    continue
            entries.sort(key=lambda entry: entry[0], reverse=True)
            return [item for _, item in entries]
        except Exception as exc:
            logger.error("Failed to list archive: %s", exc)
            return []
