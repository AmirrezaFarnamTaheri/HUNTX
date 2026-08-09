# End-to-End Performance, Intelligence & Hard-Failure Resilience Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul HUNTX end-to-end across all pipelines, formats, stores, and bot connectors to deliver max execution speed, intelligent multi-metric proxy scoring, and hard-failure resilience (circuit breakers, retry backoffs, and SQLite pool guards).

**Architecture:** 
1. Introduce an `AsyncCircuitBreaker` and `AdaptiveConcurrencyLimiter` in `src/huntx/core/resilience.py`.
2. Upgrade `TransformPipeline` with multi-threaded parallel parsing worker pools and memory-bounded batching.
3. Build `ProxyScoringEngine` in `src/huntx/core/scoring.py` combining latency, protocol validation, and historical health metrics in `StateRepo`.
4. Integrate `UnifiedOrchestrator` with auto-recovery and fallback circuit breakers.

**Tech Stack:** Python 3.11+, asyncio, SQLite, Pydantic v2, PyYAML, Pytest, Hypothesis.

## Global Constraints

- Python version floor: 3.11+
- Test framework: Pytest with 100% pass rate requirement before and after every task
- Strict typing and async exception handling without swallowing errors
- Non-blocking loop executions only

---

### Task 1: Core Resilience & Circuit Breaker Engine

**Files:**
- Create: `src/huntx/core/resilience.py`
- Create: `tests/test_resilience_engine.py`

**Interfaces:**
- Consumes: None
- Produces: `AsyncCircuitBreaker(failure_threshold, recovery_timeout)`, `AdaptiveConcurrencyLimiter(initial_concurrency, max_concurrency)`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import asyncio
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resilience_engine.py -v`
Expected: FAIL with ModuleNotFoundError or CircuitBreakerOpenError not defined.

- [ ] **Step 3: Write minimal implementation**

```python
import asyncio
import time
from typing import Callable, Any, TypeVar

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN and rejecting calls."""
    pass


class AsyncCircuitBreaker:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_resilience_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/huntx/core/resilience.py tests/test_resilience_engine.py
git commit -m "feat(core): Add AsyncCircuitBreaker for hard-failure resilience"
```

---

### Task 2: Multi-Metric Proxy Scoring Engine

**Files:**
- Create: `src/huntx/core/scoring.py`
- Create: `tests/test_proxy_scoring.py`

**Interfaces:**
- Consumes: `check_proxy_latency(proxy_uri)`
- Produces: `ProxyScoringEngine.score_proxy(proxy_record) -> float` (0.0 to 100.0)

- [ ] **Step 1: Write the failing test**

```python
import pytest
from huntx.core.scoring import ProxyScoringEngine


def test_score_proxy_calculates_quality_score():
    engine = ProxyScoringEngine()
    record = {
        "uri": "vless://example.com:443?type=ws",
        "latency_ms": 120.0,
        "historical_success_rate": 0.95,
        "protocol": "vless",
    }
    score = engine.score_proxy(record)
    assert 80.0 <= score <= 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_proxy_scoring.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Dict, Any


class ProxyScoringEngine:
    """Calculates adaptive multi-metric quality scores for proxy nodes."""

    def score_proxy(self, record: Dict[str, Any]) -> float:
        latency = record.get("latency_ms", 9999.0)
        success_rate = record.get("historical_success_rate", 0.5)

        # 1. Latency Score (0 to 50 pts)
        if latency <= 100:
            lat_score = 50.0
        elif latency <= 500:
            lat_score = 50.0 - ((latency - 100) / 400.0) * 25.0
        elif latency <= 1500:
            lat_score = 25.0 - ((latency - 500) / 1000.0) * 20.0
        else:
            lat_score = 0.0

        # 2. Historical Success Score (0 to 50 pts)
        hist_score = min(50.0, max(0.0, success_rate * 50.0))

        return round(lat_score + hist_score, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_proxy_scoring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/huntx/core/scoring.py tests/test_proxy_scoring.py
git commit -m "feat(core): Add ProxyScoringEngine for multi-metric quality evaluation"
```

---

### Task 3: Integration into UnifiedOrchestrator & Quality Gate

**Files:**
- Modify: `src/huntx/core/unified_orchestrator.py`
- Modify: `tests/test_unified_orchestrator.py`

**Interfaces:**
- Consumes: `AsyncCircuitBreaker`, `ProxyScoringEngine`
- Produces: `UnifiedOrchestrator` with active resilience and scoring engine.

- [ ] **Step 1: Write the failing test update**

```python
def test_unified_orchestrator_has_resilience_and_scoring(self):
    orch = UnifiedOrchestrator(self.config, enable_benchmarking=True)
    assert hasattr(orch, "circuit_breaker")
    assert hasattr(orch, "scoring_engine")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_unified_orchestrator.py -v`
Expected: FAIL with AttributeError.

- [ ] **Step 3: Update implementation**

In `src/huntx/core/unified_orchestrator.py`:
Add `self.circuit_breaker = AsyncCircuitBreaker()` and `self.scoring_engine = ProxyScoringEngine()` in `__init__`.

- [ ] **Step 4: Run full test suite to verify 100% green pass**

Run: `python -m pytest`
Expected: PASS (275/275 green)

- [ ] **Step 5: Commit**

```bash
git add src/huntx/core/unified_orchestrator.py tests/test_unified_orchestrator.py
git commit -m "feat(core): Integrate circuit breaker and scoring engine into UnifiedOrchestrator"
```
