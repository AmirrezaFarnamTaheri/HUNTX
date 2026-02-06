import datetime
from pathlib import Path
from .paths import REJECTS_DIR

class RejectsStore:
    def __init__(self, base_dir: Path = REJECTS_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_reject(self, source_id: str, reason: str, data: bytes):
        """Saves rejected data for debugging."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_source = "".join(c for c in source_id if c.isalnum() or c in "_-")
        safe_reason = "".join(c for c in reason if c.isalnum() or c in "_-")[:30]

        filename = f"{timestamp}_{safe_source}_{safe_reason}.dat"
        path = self.base_dir / filename

        with open(path, "wb") as f:
            f.write(data)
