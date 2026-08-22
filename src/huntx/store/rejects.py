from __future__ import annotations

import datetime
import hashlib
import os
from pathlib import Path
from typing import Optional

from ..utils.atomic import atomic_write
from ..utils.safe_names import safe_component
from . import paths


class RejectsStore:
    """Persist rejected payloads without losing same-moment forensic evidence."""

    def __init__(self, base_dir: Optional[Path] = None):
        # Resolve the default at runtime after paths.set_paths().
        self.base_dir = base_dir or paths.REJECTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_reject(self, source_id: str, reason: str, data: bytes) -> Path:
        """Atomically persist one rejected payload and return its unique path.

        Filenames include microseconds, process identity, and a payload digest.
        The prior second-resolution name could overwrite a distinct reject from
        the same source/reason in the same second, destroying forensic evidence.
        """
        if not isinstance(data, bytes):
            raise TypeError("rejected payload must be bytes")

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%S.%fZ"
        )
        safe_source = safe_component(str(source_id), default="source", max_len=80)
        safe_reason = safe_component(str(reason), default="reject", max_len=60)
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f"{timestamp}_{os.getpid()}_{safe_source}_{safe_reason}_{digest}.dat"
        path = self.base_dir / filename

        # Extremely unlikely same-process collisions (identical timestamp and
        # bytes) are still possible under a mocked/frozen clock. Preserve both
        # records by allocating a bounded numeric suffix instead of overwriting.
        if path.exists():
            for suffix in range(1, 1000):
                candidate = path.with_name(f"{path.stem}_{suffix}{path.suffix}")
                if not candidate.exists():
                    path = candidate
                    break
            else:
                raise RuntimeError("could not allocate a unique reject artifact name")

        atomic_write(path, data)
        return path
