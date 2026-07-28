from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid
from typing import Any, Optional

from .hardened_orchestrator import HardenedOrchestrator
from . import optimized_orchestrator as optimized_module
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .transform_contract import install_transform_contract
from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector

logger = logging.getLogger(__name__)

install_transform_contract()


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
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
    return _bounded_float("HUNTX_CANONICAL_RESOLVE_TIMEOUT", 20.0, 0.05, 120.0)


def _cleanup_timeout(self: OptimizedHardenedOrchestrator) -> float:
    return _bounded_float("HUNTX_TELEGRAM_CLEANUP_TIMEOUT", 10.0, 0.05, 60.0)


def _numeric_channel_id(peer: Any) -> Optional[int]:
    text = str(peer).strip()
    if text.startswith("-100") and text[4:].isdigit():
        return int(text[4:])
    return None


async def _close_canonical_connector(
    self: OptimizedHardenedOrchestrator,
    connector: Optional[WindowedTelegramUserConnector],
) -> None:
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
                self._work_queue.terminalize_source(str(source.id), "source is no longer configured as telegram_user")
                continue
            channel_id = _numeric_channel_id(config.peer)
            if channel_id is None:
                accepted.append(source)
                continue
            existing = canonical_owner.get(int(channel_id))
            if existing is None:
                canonical_owner[int(channel_id)] = str(source.id)
                accepted.append(source)
                continue
            reason = f"duplicate canonical Telegram channel {channel_id}; owned by {existing}"
            self._work_queue.terminalize_source(str(source.id), reason)
            logger.warning("[LIFO] terminalized duplicate source %s: %s", source.id, reason)
    finally:
        await _close_canonical_connector(self, connector)
    return accepted


async def _run_hardened(
    self: OptimizedHardenedOrchestrator,
    timeout: Optional[float],
    no_publish: bool,
    allow_partial_export: bool,
) -> dict[str, Any]:
    run_started = time.monotonic()
    original = list(self.config.sources)
    self._ingestion_budget_exhausted = False
    self._run_owner = uuid.uuid4().hex
    try:
        recovered = self._work_queue.recover_expired_leases()
        ingestion_sources = await self._canonical_ingestion_sources(original)
        self._source_by_id = {str(source.id): source for source in ingestion_sources}
        self.config.sources = ingestion_sources
        summary = await HardenedOrchestrator._run_hardened(
            self,
            timeout,
            no_publish,
            allow_partial_export,
        )
    finally:
        self.config.sources = original
        self._ingestion_stop_monotonic = None
    summary["lifo_recovered_leases"] = recovered
    summary["duration_seconds"] = float(summary.get("duration_seconds", 0.0)) + (time.monotonic() - run_started)
    return summary


def apply_runtime_resilience() -> None:
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
