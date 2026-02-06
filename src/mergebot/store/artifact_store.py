import hashlib
import os
from pathlib import Path
from typing import Optional
from .paths import ARTIFACT_STORE_DIR, DATA_DIR

class ArtifactStore:
    def __init__(self, base_dir: Path = ARTIFACT_STORE_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = DATA_DIR / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(self, name: str, data: bytes) -> str:
        """
        Saves a built artifact using hash-based naming (for internal history).
        Returns the SHA256 of the content.
        """
        sha256 = hashlib.sha256(data).hexdigest()

        target_dir = self.base_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / f"{sha256}.bin"

        if not target_path.exists():
            tmp_path = target_path.with_suffix(".tmp")
            with open(tmp_path, "wb") as f:
                f.write(data)
            tmp_path.rename(target_path)

        return sha256

    def save_output(self, route_name: str, fmt: str, data: bytes) -> str:
        """
        Saves the artifact in a user-friendly way for distribution/testing.
        Location: DATA_DIR/output/{route_name}/{route_name}.{fmt}
        """
        target_dir = self.output_dir / route_name
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{route_name}.{fmt}"
        target_path = target_dir / filename

        with open(target_path, "wb") as f:
            f.write(data)

        return str(target_path)

    def get_artifact(self, name: str, sha256: str) -> Optional[bytes]:
        path = self.base_dir / name / f"{sha256}.bin"
        if path.exists():
            return path.read_bytes()
        return None
