"""Observed HTTP feed reliability; never evidence of working proxy traffic."""
from __future__ import annotations

import math
import time
from typing import Any, Mapping

WINDOW_SIZE = 64
WINDOW_AGE_SECONDS = 30 * 24 * 3600


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


def _recent_observations(state: Mapping[str, Any], now: int) -> list[dict[str, Any]]:
    """Bound hostile or corrupt persisted state before computing statistics."""
    raw = state.get("retrieval_history")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[-WINDOW_SIZE:]:
        if not isinstance(item, dict) or type(item.get("ok")) is not bool:
            continue
        at = _observed_timestamp(item.get("at"), now)
        if at is None or at > now or now - at > WINDOW_AGE_SECONDS:
            continue
        result.append({
            "at": at,
            "ok": item["ok"],
            "nodes": _bounded_count(item.get("nodes")),
            "cache": bool(item.get("cache") is True),
        })
    return result


def append_retrieval_observation(
    state: Mapping[str, Any],
    *,
    success: bool,
    now: int | None = None,
    nodes: int = 0,
    cache_revalidated: bool = False,
) -> list[dict[str, Any]]:
    """Return a bounded, cache-safe history; source totals live separately.

    Each run adds exactly one result after the fetch/parser finishes. A stale
    success cannot hide a recent failure streak, and raw URLs/credentials are
    never saved in this ledger.
    """
    clock = int(time.time()) if now is None else int(now)
    if clock <= 0:
        raise ValueError("observation timestamp must be positive")
    recent = _recent_observations(state, clock)
    recent.append({
        "at": clock,
        "ok": bool(success),
        "nodes": _bounded_count(nodes) if success else 0,
        "cache": bool(cache_revalidated) if success else False,
    })
    return recent[-WINDOW_SIZE:]


def _wilson_lower(successes: int, samples: int) -> float:
    if not samples:
        return 0.0
    p = successes / samples
    z = 1.96
    z2 = z * z
    numerator = p + z2 / (2 * samples) - z * math.sqrt(
        p * (1 - p) / samples + z2 / (4 * samples * samples)
    )
    return round(max(0.0, min(1.0, numerator / (1 + z2 / samples))), 4)


def summarize_source_reliability(
    state: Mapping[str, Any], *, now: int | None = None
) -> dict[str, Any]:
    """Separate confidence in HTTP retrieval from proxy reachability.

    Historic lifetime counters support continuity across schema upgrades.
    The recent bounded Wilson estimate prevents long-ago successes from
    masking degraded upstreams. Neither metric authenticates a proxy.
    """
    clock = int(time.time()) if now is None else int(now)
    successes = _bounded_count(state.get("previous_successes"))
    failures = _bounded_count(state.get("total_failures"))
    samples = successes + failures
    last_success = _observed_timestamp(state.get("last_success_at"), clock)
    last_failure = _observed_timestamp(state.get("last_failed_at"), clock)
    streak = _bounded_count(state.get("consecutive_failures"))
    age = max(0, clock - last_success) if last_success is not None else None
    if age is None:
        freshness = "unobserved"
    elif age > 2 * 24 * 3600:
        freshness = "stale"
    elif streak:
        freshness = "degraded"
    else:
        freshness = "recent"

    events = _recent_observations(state, clock)
    recent_successes = sum(1 for event in events if event["ok"])
    recent_count = len(events)
    lower = _wilson_lower(recent_successes, recent_count)
    if freshness == "recent":
        freshness_weight = 1.0
    elif freshness == "degraded":
        freshness_weight = 0.5
    else:
        freshness_weight = 0.0
    return {
        "kind": "source_http_availability_only",
        "successes": successes,
        "failures": failures,
        "consecutive_failures": streak,
        "wilson_lower_bound": _wilson_lower(successes, samples),
        "rolling_samples": recent_count,
        "rolling_successes": recent_successes,
        "rolling_success_rate": (
            round(recent_successes / recent_count, 4) if recent_count else None
        ),
        "rolling_wilson_lower_bound": lower,
        "cache_revalidations": sum(1 for event in events if event["ok"] and event["cache"]),
        "ranking_score": round(100 * lower * freshness_weight, 2),
        "last_success_at": last_success,
        "last_failed_at": last_failure,
        "success_age_seconds": age,
        "freshness": freshness,
        "evidence": "feed_retrieval_not_authenticated_proxy",
    }


def prioritize_http_sources(
    sources: list[Any],
    states: Mapping[str, Mapping[str, Any]],
    *,
    now: int | None = None,
) -> list[Any]:
    """Give old/untried feeds exploration opportunities without starving Telegram.

    Only HTTP source slots are reordered. Every source remains present and
    subject to the same validation and publication rules. The oldest-attempted
    source gets one exploration slot; the rest are ranked by recent evidence.
    A failed source is retried, not forgotten forever.
    """
    clock = int(time.time()) if now is None else int(now)
    locations = [
        i for i, source in enumerate(sources)
        if getattr(source, "type", None) == "http_subscription"
    ]
    if len(locations) < 2:
        return list(sources)
    feeds = [sources[i] for i in locations]

    def state_of(source: Any) -> Mapping[str, Any]:
        value = states.get(str(source.id), {})
        return value if isinstance(value, Mapping) else {}

    def attempt_time(source: Any) -> int:
        state = state_of(source)
        attempts = [
            _observed_timestamp(state.get(key), clock) or 0
            for key in ("checked_at", "last_failed_at")
        ]
        return max(attempts)

    exploration = min(feeds, key=lambda source: (attempt_time(source), str(source.id)))
    remaining = [source for source in feeds if source is not exploration]
    ranked = sorted(
        remaining,
        key=lambda source: (
            -summarize_source_reliability(state_of(source), now=clock)["ranking_score"],
            attempt_time(source),
            str(source.id),
        ),
    )
    result = list(sources)
    for slot, source in zip(locations, [exploration, *ranked]):
        result[slot] = source
    return result
