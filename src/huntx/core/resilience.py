from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit breaker rejects a call without invoking it."""


class AsyncCircuitBreaker:
    """Concurrency-safe circuit breaker for asynchronous operations.

    Failures are consecutive: any successful CLOSED-state call resets the
    counter. After the recovery timeout exactly one HALF_OPEN probe is allowed;
    concurrent callers continue to fail fast until that probe succeeds.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int):
            raise ValueError("failure_threshold must be a positive integer")
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        try:
            timeout = float(recovery_timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("recovery_timeout must be a finite positive number") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("recovery_timeout must be a finite positive number")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = timeout
        self.failure_count = 0
        self.state = self.CLOSED
        self.last_state_change = time.monotonic()
        self._lock = asyncio.Lock()
        self._half_open_in_flight = False

    async def _admit(self) -> bool:
        """Return whether this call is the exclusive HALF_OPEN probe."""
        async with self._lock:
            now = time.monotonic()
            if self.state == self.OPEN:
                if now - self.last_state_change < self.recovery_timeout:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
                self.state = self.HALF_OPEN
                self.last_state_change = now
                self._half_open_in_flight = True
                return True

            if self.state == self.HALF_OPEN:
                if self._half_open_in_flight:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker HALF_OPEN probe is already in progress"
                    )
                self._half_open_in_flight = True
                return True

            return False

    async def _record_success(self, was_half_open_probe: bool) -> None:
        async with self._lock:
            if was_half_open_probe or self.state == self.HALF_OPEN:
                self.state = self.CLOSED
                self.last_state_change = time.monotonic()
                self._half_open_in_flight = False
            self.failure_count = 0

    async def _record_failure(self, was_half_open_probe: bool) -> None:
        async with self._lock:
            now = time.monotonic()
            if was_half_open_probe or self.state == self.HALF_OPEN:
                self.failure_count = max(self.failure_count + 1, self.failure_threshold)
                self.state = self.OPEN
                self.last_state_change = now
                self._half_open_in_flight = False
                return

            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                self.last_state_change = now

    async def _abort_probe(self, was_half_open_probe: bool) -> None:
        """Release HALF_OPEN ownership when a recovery probe is cancelled/aborted."""
        if not was_half_open_probe:
            return
        async with self._lock:
            self.failure_count = max(self.failure_count, self.failure_threshold)
            self.state = self.OPEN
            self.last_state_change = time.monotonic()
            self._half_open_in_flight = False

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Invoke one async operation under the breaker state contract."""
        was_half_open_probe = await self._admit()
        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            await self._abort_probe(was_half_open_probe)
            raise
        except Exception:
            await self._record_failure(was_half_open_probe)
            raise
        except BaseException:
            # SystemExit/KeyboardInterrupt are not service failures, but an
            # exclusive HALF_OPEN probe still must release ownership.
            await self._abort_probe(was_half_open_probe)
            raise
        await self._record_success(was_half_open_probe)
        return result
