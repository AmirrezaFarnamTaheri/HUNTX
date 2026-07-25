# src/huntx/utils/profiler.py
"""Lightweight profiling helpers for regression benchmarks."""
from __future__ import annotations

import os
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def wall_clock(fn: Callable[..., T], *args: Any, **kwargs: Any) -> tuple[T, float]:
    """Call *fn* and return (result, elapsed_wall_seconds)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


def rss_mb() -> float:
    """Return current process RSS in MB. Returns 0.0 on unsupported platforms."""
    try:
        import resource  # type: ignore[import]
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # type: ignore[attr-defined]
    except ImportError:
        try:
            import psutil  # type: ignore[import]
            return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except ImportError:
            return 0.0
