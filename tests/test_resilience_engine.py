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

    # Third call should fail fast with CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(faulty_call)
