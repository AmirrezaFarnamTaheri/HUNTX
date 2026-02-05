import hashlib
from pathlib import Path
from typing import Optional
from .paths import ARTIFACT_STORE_DIR

class ArtifactStore:
    def __init__(self, base_dir: Path = ARTIFACT_STORE_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(self, name: str, data: bytes) -> str:
        """
        Saves a built artifact.
        Returns the SHA256 of the content.
        """
        sha256 = hashlib.sha256(data).hexdigest()
        # We might want to keep history, so we can save as name_sha256 or just by hash
        # For this implementation, let's save by hash but organized by name

        target_dir = self.base_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / f"{sha256}.bin"

        if not target_path.exists():
            tmp_path = target_path.with_suffix(".tmp")
            with open(tmp_path, "wb") as f:
                f.write(data)
            tmp_path.rename(target_path)

        return sha256

    def get_artifact(self, name: str, sha256: str) -> Optional[bytes]:
        path = self.base_dir / name / f"{sha256}.bin"
        if path.exists():
            return path.read_bytes()
        return None
