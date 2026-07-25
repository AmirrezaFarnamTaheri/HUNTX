import asyncio
import time
from typing import Callable, Any, TypeVar

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN and rejecting calls."""
    pass


class AsyncCircuitBreaker:
    """Circuit breaker for async operations preventing cascade failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_state_change = time.monotonic()

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        now = time.monotonic()
        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        try:
            res = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return res
        except Exception:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = now
            raise
