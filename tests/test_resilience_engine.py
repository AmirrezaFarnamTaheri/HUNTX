import asyncio

import pytest

from huntx.core.resilience import AsyncCircuitBreaker, CircuitBreakerOpenError


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    cb = AsyncCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    async def faulty_call():
        raise ValueError("Service down")

    with pytest.raises(ValueError):
        await cb.call(faulty_call)
    with pytest.raises(ValueError):
        await cb.call(faulty_call)
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(faulty_call)


@pytest.mark.asyncio
async def test_success_resets_consecutive_failure_count():
    cb = AsyncCircuitBreaker(failure_threshold=2, recovery_timeout=1)

    async def fail():
        raise RuntimeError("boom")

    async def succeed():
        return "ok"

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.failure_count == 1

    assert await cb.call(succeed) == "ok"
    assert cb.failure_count == 0

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == cb.CLOSED


@pytest.mark.asyncio
async def test_half_open_allows_exactly_one_concurrent_probe():
    cb = AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

    async def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    await asyncio.sleep(0.02)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def probe():
        entered.set()
        await release.wait()
        return "recovered"

    first = asyncio.create_task(cb.call(probe))
    await entered.wait()

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(probe)

    release.set()
    assert await first == "recovered"
    assert cb.state == cb.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_cancelled_half_open_probe_reopens_and_releases_ownership():
    cb = AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

    async def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    await asyncio.sleep(0.02)

    entered = asyncio.Event()

    async def probe():
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(cb.call(probe))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cb.state == cb.OPEN
    assert cb._half_open_in_flight is False
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(probe)


@pytest.mark.parametrize(
    ("threshold", "timeout"),
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, float("nan"))],
)
def test_circuit_breaker_rejects_invalid_configuration(threshold, timeout):
    with pytest.raises(ValueError):
        AsyncCircuitBreaker(failure_threshold=threshold, recovery_timeout=timeout)
