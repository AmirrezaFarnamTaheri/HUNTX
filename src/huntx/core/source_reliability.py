"""Observed HTTP feed reliability; not a proxy reachability or security score."""
from __future__ import annotations

import math
import time
from typing import Any, Mapping


def _bounded_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        return 0
    return max(0, min(number, 1_000_000))


def _observed_timestamp(value: Any, now: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if 0 < timestamp <= now + 300:
        return timestamp
    return None


def summarize_source_reliability(
    state: Mapping[str, Any], *, now: int | None = None
) -> dict[str, Any]:
    """Report confidence in *feed retrieval*, never proxy connectivity.

    Wilson's lower bound prevents a single successful fetch from becoming a
    high reliability grade. Stale historical success cannot appear fresh.
    """
    clock = int(time.time()) if now is None else int(now)
    successes = _bounded_count(state.get("previous_successes"))
    failures = _bounded_count(state.get("total_failures"))
    samples = successes + failures
    last_success = _observed_timestamp(state.get("last_success_at"), clock)
    last_failure = _observed_timestamp(state.get("last_failed_at"), clock)
    streak = _bounded_count(state.get("consecutive_failures"))
    if samples:
        p = successes / samples
        z = 1.96
        z2 = z * z
        bound = (
            p + z2 / (2 * samples) -
            z * math.sqrt(p * (1 - p) / samples + z2 / (4 * samples * samples))
        ) / (1 + z2 / samples)
        lower_bound = round(max(0.0, min(1.0, bound)), 4)
    else:
        lower_bound = 0.0
    age = max(0, clock - last_success) if last_success is not None else None
    if age is None:
        freshness = "unobserved"
    elif age > 2 * 24 * 3600:
        freshness = "stale"
    elif streak:
        freshness = "degraded"
    else:
        freshness = "recent"
    return {
        "kind": "source_http_availability_only",
        "successes": successes,
        "failures": failures,
        "consecutive_failures": streak,
        "wilson_lower_bound": lower_bound,
        "last_success_at": last_success,
        "last_failed_at": last_failure,
        "success_age_seconds": age,
        "freshness": freshness,
    }
