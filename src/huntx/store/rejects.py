import datetime
from pathlib import Path
from typing import Optional
from ..utils.atomic import atomic_write
from . import paths


class RejectsStore:
    def __init__(self, base_dir: Optional[Path] = None):
        # IMPORTANT: resolve the default at runtime (after paths.set_paths()),
        # mirroring RawStore/ArtifactStore. Binding paths.REJECTS_DIR as a
        # default argument would capture the pre-configuration directory at
        # import time and silently write rejects to the wrong location.
        self.base_dir = base_dir or paths.REJECTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_reject(self, source_id: str, reason: str, data: bytes):
        """Saves rejected data for debugging."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_source = "".join(c for c in source_id if c.isalnum() or c in "_-")
        safe_reason = "".join(c for c in reason if c.isalnum() or c in "_-")[:30]

        filename = f"{timestamp}_{safe_source}_{safe_reason}.dat"
        path = self.base_dir / filename

        atomic_write(path, data)
