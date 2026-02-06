import hashlib
import logging
import os
from pathlib import Path
from typing import Optional
from .paths import ARTIFACT_STORE_DIR, DATA_DIR

logger = logging.getLogger(__name__)

class ArtifactStore:
    def __init__(self, base_dir: Path = ARTIFACT_STORE_DIR):
        self.base_dir = base_dir
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir = DATA_DIR / "output"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"ArtifactStore initialized at {self.base_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize ArtifactStore directories: {e}")
            raise

    def save_artifact(self, name: str, data: bytes) -> str:
        """
        Saves a built artifact using hash-based naming (for internal history).
        Returns the SHA256 of the content.
        """
        try:
            sha256 = hashlib.sha256(data).hexdigest()

            target_dir = self.base_dir / name
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / f"{sha256}.bin"

            if not target_path.exists():
                tmp_path = target_path.with_suffix(".tmp")
                with open(tmp_path, "wb") as f:
                    f.write(data)
                tmp_path.rename(target_path)
                logger.debug(f"Saved internal artifact {sha256} for route '{name}'")

            return sha256
        except Exception as e:
            logger.exception(f"Failed to save internal artifact for '{name}': {e}")
            raise

    def save_output(self, route_name: str, fmt: str, data: bytes) -> str:
        """
        Saves the artifact in a user-friendly way for distribution/testing.
        Location: DATA_DIR/output/{route_name}/{route_name}.{fmt}
        """
        try:
            target_dir = self.output_dir / route_name
            target_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{route_name}.{fmt}"
            target_path = target_dir / filename

            with open(target_path, "wb") as f:
                f.write(data)

            logger.info(f"Saved user-facing artifact: {target_path}")
            return str(target_path)
        except Exception as e:
            logger.exception(f"Failed to save output artifact '{route_name}.{fmt}': {e}")
            raise

    def get_artifact(self, name: str, sha256: str) -> Optional[bytes]:
        try:
            path = self.base_dir / name / f"{sha256}.bin"
            if path.exists():
                return path.read_bytes()
            logger.warning(f"Artifact {sha256} not found for route '{name}'")
            return None
        except Exception as e:
            logger.error(f"Error retrieving artifact {sha256} for '{name}': {e}")
            return None
