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
async def test_circuit_breaker_allows_only_one_half_open_probe():
    cb = AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0)

    async def fail():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    entered = asyncio.Event()
    release = asyncio.Event()

    async def recover():
        entered.set()
        await release.wait()
        return "ok"

    first = asyncio.create_task(cb.call(recover))
    await entered.wait()

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(recover)

    release.set()
    assert await first == "ok"
    assert cb.state == "CLOSED"
