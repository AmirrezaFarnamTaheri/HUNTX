import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker rejects a call while unavailable."""


class AsyncCircuitBreaker:
    """Protect async dependencies with synchronized circuit-breaker state."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        """Create a breaker with a positive threshold and non-negative timeout."""
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be greater than zero")
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout must be non-negative")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_state_change = time.monotonic()
        self._state_lock = asyncio.Lock()
        self._half_open_probe_in_flight = False

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run one async operation or reject it while the circuit is unavailable.

        CLOSED calls are admitted normally. Once the failure threshold is reached,
        the breaker moves to OPEN and rejects calls until the recovery timeout has
        elapsed. Exactly one caller is then reserved as the HALF_OPEN probe; all
        concurrent callers remain rejected until that probe succeeds or fails.
        """
        probe_reserved = False
        async with self._state_lock:
            if self.state == "OPEN":
                elapsed = time.monotonic() - self.last_state_change
                if elapsed < self.recovery_timeout:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
                if self._half_open_probe_in_flight:
                    raise CircuitBreakerOpenError("Circuit breaker recovery probe is in progress")
                self.state = "HALF_OPEN"
                self._half_open_probe_in_flight = True
                probe_reserved = True
            elif self.state == "HALF_OPEN":
                raise CircuitBreakerOpenError("Circuit breaker recovery probe is in progress")

        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            if probe_reserved:
                async with self._state_lock:
                    self.state = "OPEN"
                    self.last_state_change = time.monotonic()
                    self._half_open_probe_in_flight = False
            raise
        except Exception:
            async with self._state_lock:
                if probe_reserved:
                    self.failure_count = self.failure_threshold
                    self.state = "OPEN"
                    self.last_state_change = time.monotonic()
                    self._half_open_probe_in_flight = False
                else:
                    self.failure_count += 1
                    if self.failure_count >= self.failure_threshold:
                        self.state = "OPEN"
                        self.last_state_change = time.monotonic()
            raise

        async with self._state_lock:
            self.failure_count = 0
            if probe_reserved:
                self.state = "CLOSED"
                self._half_open_probe_in_flight = False
        return result
