from __future__ import annotations

import time


class DeadlineExceeded(TimeoutError):
    """Raised when the run-wide monotonic deadline has been exhausted."""


class Deadline:
    """One monotonic deadline shared across nested blocking operations."""

    def __init__(self, timeout_seconds: float | None) -> None:
        self._expires_at = (
            None if timeout_seconds is None else time.monotonic() + max(0.0, float(timeout_seconds))
        )

    def remaining_seconds(self) -> float | None:
        if self._expires_at is None:
            return None
        return max(0.0, self._expires_at - time.monotonic())

    def expired(self) -> bool:
        remaining = self.remaining_seconds()
        return remaining is not None and remaining <= 0.0

    def raise_if_expired(self, stage: str = "operation") -> None:
        if self.expired():
            raise DeadlineExceeded(f"Global deadline exhausted during {stage}")

    def clamp_timeout(self, ceiling_seconds: float) -> float:
        self.raise_if_expired("blocking I/O")
        remaining = self.remaining_seconds()
        if remaining is None:
            return float(ceiling_seconds)
        return max(0.001, min(float(ceiling_seconds), remaining))

    def sleep(self, seconds: float) -> None:
        self.raise_if_expired("retry backoff")
        remaining = self.remaining_seconds()
        requested = max(0.0, float(seconds))
        if remaining is not None and requested >= remaining:
            raise DeadlineExceeded("Global deadline would expire during retry backoff")
        time.sleep(requested)
