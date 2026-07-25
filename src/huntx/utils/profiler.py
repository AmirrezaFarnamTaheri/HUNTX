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
    """Return current process RSS in MiB, or 0.0 when unavailable."""
    try:
        import psutil  # type: ignore[import]
    except ImportError:
        return 0.0

    try:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except (OSError, psutil.Error):
        return 0.0
