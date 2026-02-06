import hashlib
from pathlib import Path
from typing import Optional
from .paths import RAW_STORE_DIR

class RawStore:
    def __init__(self, base_dir: Path = RAW_STORE_DIR):
        self.base_dir = base_dir

    def save(self, data: bytes) -> str:
        """Saves data to a file named by its SHA256 hash. Returns the hash."""
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

        return sha256

    def get(self, sha256: str) -> Optional[bytes]:
        """Retrieves data by hash."""
        prefix = sha256[:2]
        path = self.base_dir / prefix / sha256
        if path.exists():
            return path.read_bytes()
        return None

    def exists(self, sha256: str) -> bool:
        prefix = sha256[:2]
        return (self.base_dir / prefix / sha256).exists()
