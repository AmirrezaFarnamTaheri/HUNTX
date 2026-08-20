from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid
from typing import Any, Optional

from . import optimized_orchestrator as optimized_module
from .dev_manifest_contract import install_dev_manifest_contract
from .hardened_orchestrator import HardenedOrchestrator
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .orchestrator import Orchestrator
from .transform_contract import install_transform_contract
from ..connectors.telegram_user.failure_policy import is_permanent_telegram_peer_error
from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector

logger = logging.getLogger(__name__)

install_transform_contract()
install_dev_manifest_contract(Orchestrator)


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a finite bounded floating-point environment setting."""
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        value = default
    if not math.isfinite(value):
        logger.warning("Non-finite %s=%r; using %s", name, raw, default)
        value = default
    return max(minimum, min(value, maximum))


def _canonical_timeout(self: OptimizedHardenedOrchestrator) -> float:
    """Return the bounded Telegram canonical-channel resolution timeout."""
    return _bounded_float("HUNTX_CANONICAL_RESOLVE_TIMEOUT", 20.0, 0.05, 120.0)


def _cleanup_timeout(self: OptimizedHardenedOrchestrator) -> float:
    """Return the bounded Telegram cleanup timeout."""
    return _bounded_float("HUNTX_TELEGRAM_CLEANUP_TIMEOUT", 10.0, 0.05, 60.0)


def _numeric_channel_id(peer: Any) -> Optional[int]:
    """Extract a canonical numeric Telegram channel ID when directly available."""
    text = str(peer).strip()
    if text.startswith("-100") and text[4:].isdigit():
        return int(text[4:])
    return None


async def _close_canonical_connector(
    self: OptimizedHardenedOrchestrator,
    connector: Optional[WindowedTelegramUserConnector],
) -> None:
    """Close the reusable canonical-resolution connector within a bounded timeout."""
    if connector is None:
        return
    try:
        await asyncio.wait_for(
            connector.__aexit__(None, None, None),
            timeout=_cleanup_timeout(self),
        )
    except asyncio.TimeoutError:
        logger.error("[LIFO] Timed out closing canonical Telegram client")
    except Exception:
        logger.exception("[LIFO] Failed closing canonical Telegram client")


async def _canonical_ingestion_sources(
    self: OptimizedHardenedOrchestrator,
    sources: list[Any],
) -> list[Any]:
    """Return reachable, canonicalized Telegram sources plus direct sources."""
    accepted: list[Any] = []
    canonical_owner: dict[int, str] = {}
    connector: Optional[WindowedTelegramUserConnector] = None
    connector_key: Optional[tuple[int, str, str]] = None

    try:
        for source in sources:
            if getattr(source, "type", None) != "telegram_user":
                accepted.append(source)
                continue

            config = getattr(source, "telegram_user", None)
            if config is None:
                self._work_queue.terminalize_source(
                    str(source.id),
                    "source is no longer configured as telegram_user",
                )
                continue

            configured_channel_id = _numeric_channel_id(config.peer)
            if configured_channel_id is not None:
                existing = canonical_owner.get(configured_channel_id)
                if existing is not None:
                    reason = (
                        f"duplicate canonical Telegram channel {configured_channel_id}; "
                        f"owned by {existing}"
                    )
                    terminalized = self._work_queue.terminalize_source(
                        str(source.id),
                        reason,
                    )
                    logger.warning(
                        "[LIFO] Skipping numeric alias source %s for canonical "
                        "channel %s already owned by %s; terminalized=%s",
                        source.id,
                        configured_channel_id,
                        existing,
                        terminalized,
                    )
                    continue

            stop = getattr(self, "_ingestion_stop_monotonic", None)
            remaining = None if stop is None else stop - time.monotonic()
            if remaining is not None and remaining <= 0:
                self._ingestion_budget_exhausted = True
                accepted.append(source)
                continue

            operation_timeout = _canonical_timeout(self)
            if remaining is not None:
                operation_timeout = max(0.01, min(operation_timeout, remaining))

            key = (int(config.api_id), str(config.api_hash), str(config.session))
            if connector is None or connector_key != key:
                await _close_canonical_connector(self, connector)
                connector_class = optimized_module.WindowedTelegramUserConnector
                connector = connector_class(
                    api_id=config.api_id,
                    api_hash=config.api_hash,
                    session=config.session,
                    peer=config.peer,
                    state=None,
                    fetch_windows=None,
                )
                connector_key = key
                try:
                    await asyncio.wait_for(
                        connector.__aenter__(),
                        timeout=operation_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "[LIFO] Timed out acquiring Telegram session for %s; preserving source",
                        source.id,
                    )
                    connector = None
                    connector_key = None
                    accepted.append(source)
                    continue
                except Exception:
                    logger.exception(
                        "[LIFO] Failed acquiring Telegram session for %s; preserving source",
                        source.id,
                    )
                    connector = None
                    connector_key = None
                    accepted.append(source)
                    continue

            connector.peer = config.peer
            try:
                resolved_channel_id = await asyncio.wait_for(
                    connector.resolve_channel_id_async(),
                    timeout=operation_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[LIFO] Canonical resolution timed out for %s after %.2fs; preserving source",
                    source.id,
                    operation_timeout,
                )
                await _close_canonical_connector(self, connector)
                connector = None
                connector_key = None
                accepted.append(source)
                continue
            except Exception as exc:
                if is_permanent_telegram_peer_error(exc):
                    reason = (
                        "permanent Telegram peer failure during canonical preflight: "
                        f"{type(exc).__name__}"
                    )
                    terminalized = self._work_queue.terminalize_source(
                        str(source.id),
                        reason,
                    )
                    logger.warning(
                        "[LIFO] Excluding permanently unavailable Telegram source=%s "
                        "type=%s terminalized=%s",
                        source.id,
                        type(exc).__name__,
                        terminalized,
                    )
                    continue

                logger.exception(
                    "[LIFO] Could not resolve canonical channel for %s; preserving source",
                    source.id,
                )
                await _close_canonical_connector(self, connector)
                connector = None
                connector_key = None
                accepted.append(source)
                continue

            if resolved_channel_id is None and configured_channel_id is not None:
                reason = "numeric Telegram peer is unreachable with the configured session"
                terminalized = self._work_queue.terminalize_source(
                    str(source.id),
                    reason,
                )
                logger.warning(
                    "[LIFO] Excluding unreachable numeric Telegram source=%s "
                    "channel=%s terminalized=%s",
                    source.id,
                    configured_channel_id,
                    terminalized,
                )
                continue

            channel_id = (
                int(resolved_channel_id)
                if resolved_channel_id is not None
                else configured_channel_id
            )
            if channel_id is None:
                accepted.append(source)
                continue

            existing = canonical_owner.get(int(channel_id))
            if existing is None:
                canonical_owner[int(channel_id)] = str(source.id)
                accepted.append(source)
                continue

            reason = f"duplicate canonical Telegram channel {channel_id}; owned by {existing}"
            terminalized = self._work_queue.terminalize_source(str(source.id), reason)
            logger.warning(
                "[LIFO] Skipping alias source %s for canonical channel %s already owned by %s; terminalized=%s",
                source.id,
                channel_id,
                existing,
                terminalized,
            )
    finally:
        await _close_canonical_connector(self, connector)

    return accepted


async def _run_hardened(
    self: OptimizedHardenedOrchestrator,
    timeout: Optional[float],
    no_publish: bool,
    allow_partial_export: bool,
) -> dict[str, Any]:
    """Run the resilient optimized pipeline without bypassing source trust policy."""
    run_started = time.monotonic()
    original = list(self.config.sources)
    approved = [
        source
        for source in original
        if getattr(source, "publication_eligible", True)
    ]
    rejected = [
        source
        for source in original
        if not getattr(source, "publication_eligible", True)
    ]
    for source in rejected:
        terminalized = self._work_queue.terminalize_source(
            str(source.id),
            "source is not publication-approved",
        )
        if terminalized:
            logger.warning(
                "[LIFO] Terminalized %s queued work item(s) for unapproved source %s",
                terminalized,
                source.id,
            )

    self._ingestion_budget_exhausted = False
    self._window_pages = 0
    self._window_completions = 0
    self._window_failures = 0
    self._reset_investigation_metrics()
    self._run_owner = uuid.uuid4().hex
    self._completion_buffer_seconds = self._completion_buffer(timeout)

    if timeout is not None:
        ingestion_budget = max(0.0, timeout - self._completion_buffer_seconds)
        self._ingestion_stop_monotonic = run_started + ingestion_budget
    else:
        ingestion_budget = None
        self._ingestion_stop_monotonic = None

    seed: dict[str, int] = {
        "campaign_id": 0,
        "anchor_ts": 0,
        "target_start_ts": 0,
        "inserted": 0,
    }
    preflight_seconds = 0.0
    summary: dict[str, Any]
    ingestion_sources: list[Any] = []
    try:
        recovered = self._work_queue.recover_expired_leases()
        ingestion_sources = await self._canonical_ingestion_sources(approved)
        self._source_by_id = {str(source.id): source for source in ingestion_sources}
        self.config.sources = ingestion_sources
        seed = self._work_queue.seed_rolling_horizon(
            ingestion_sources,
            lookback_seconds=self._lookback_seconds(),
            window_seconds=self._window_seconds(),
        )
        preflight_seconds = time.monotonic() - run_started
        remaining_total = None if timeout is None else max(0.0, timeout - preflight_seconds)
        logger.info(
            "[Orchestrator] budgets total=%s remaining_after_preflight=%s ingestion=%s "
            "completion_buffer=%s preflight_seconds=%.3f lifo_campaign=%s seeded=%s "
            "recovered_leases=%s approved=%s rejected=%s canonical=%s",
            timeout,
            remaining_total,
            ingestion_budget,
            self._completion_buffer_seconds,
            preflight_seconds,
            seed["campaign_id"],
            seed["inserted"],
            recovered,
            len(approved),
            len(rejected),
            len(ingestion_sources),
        )
        summary = await HardenedOrchestrator._run_hardened(
            self,
            remaining_total,
            no_publish,
            allow_partial_export,
        )
    finally:
        windowed = getattr(self, "_windowed_ingestion", None)
        if windowed is not None:
            await windowed.close(_cleanup_timeout(self))
        released = self._work_queue.release_owner(self._run_owner)
        if released:
            logger.warning("[LIFO] Released %s unfinished lease(s) to residue", released)
        self.config.sources = original
        self._ingestion_stop_monotonic = None

    residue = self._work_queue.summary()
    remaining_residue = int(residue.get("remaining", 0))
    summary["duration_seconds"] = float(summary.get("duration_seconds", 0.0)) + preflight_seconds
    summary["preflight_seconds"] = preflight_seconds
    summary["completion_buffer_seconds"] = self._completion_buffer_seconds
    summary["ingestion_budget_seconds"] = ingestion_budget
    summary["ingestion_budget_exhausted"] = self._ingestion_budget_exhausted
    summary["lifo_campaign_id"] = seed["campaign_id"]
    summary["lifo_anchor_ts"] = seed["anchor_ts"]
    summary["lifo_target_start_ts"] = seed["target_start_ts"]
    summary["lifo_windows_seeded"] = seed["inserted"]
    summary["lifo_pages_processed"] = self._window_pages
    summary["lifo_windows_completed"] = self._window_completions
    summary["lifo_window_failures"] = self._window_failures
    summary["lifo_residue"] = residue
    summary.update(self._investigation_metrics())
    summary["ingest_skipped_due_to_budget"] = (
        remaining_residue if self._ingestion_budget_exhausted else 0
    )
    summary["configured_approved_sources"] = len(approved)
    summary["excluded_sources"] = len(rejected)
    summary["canonical_ingestion_sources"] = len(ingestion_sources)

    if self._ingestion_budget_exhausted and summary.get("status") == "completed":
        summary["status"] = "partial"
    if self._ingestion_budget_exhausted:
        summary["partial_reason"] = "ingestion_budget_exhausted"
    elif remaining_residue > 0 and summary.get("status") == "completed":
        summary["status"] = "partial"
        summary["partial_reason"] = "ingestion_residue_remaining"

    logger.info("[Orchestrator] optimized final summary=%s", summary)
    return summary


async def _disabled_legacy_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Fail closed if obsolete direct legacy orchestration is invoked."""
    raise RuntimeError(
        "_run_async_legacy is disabled; use run()/_run_async() through the hardened runtime"
    )


def apply_runtime_resilience() -> None:
    """Install resilient runtime overrides exactly once."""
    cls = OptimizedHardenedOrchestrator
    if getattr(cls, "_runtime_resilience_applied", False):
        return
    cls._canonical_timeout = _canonical_timeout  # type: ignore[attr-defined]
    cls._cleanup_timeout = _cleanup_timeout  # type: ignore[attr-defined]
    cls._numeric_channel_id = staticmethod(_numeric_channel_id)  # type: ignore[attr-defined]
    cls._close_canonical_connector = _close_canonical_connector  # type: ignore[attr-defined]
    cls._canonical_ingestion_sources = _canonical_ingestion_sources  # type: ignore[method-assign]
    cls._run_hardened = _run_hardened  # type: ignore[method-assign]
    cls._runtime_resilience_applied = True  # type: ignore[attr-defined]
    Orchestrator._run_async_legacy = _disabled_legacy_run  # type: ignore[method-assign]
