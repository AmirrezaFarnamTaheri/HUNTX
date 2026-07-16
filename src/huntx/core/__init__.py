"""Core orchestration package."""

from typing import Any

from . import optimized_orchestrator as _optimized
from . import runtime_resilience as _runtime


_original_canonical_sources = _runtime._canonical_ingestion_sources


async def _canonical_sources_with_compatible_connector(
    self: Any,
    sources: list[Any],
) -> list[Any]:
    """Honor the public connector symbol used by existing integrations/tests."""
    previous = _runtime.WindowedTelegramUserConnector
    _runtime.WindowedTelegramUserConnector = _optimized.WindowedTelegramUserConnector
    try:
        return await _original_canonical_sources(self, sources)
    finally:
        _runtime.WindowedTelegramUserConnector = previous


_runtime._canonical_ingestion_sources = _canonical_sources_with_compatible_connector
_runtime.apply_runtime_resilience()

apply_runtime_resilience = _runtime.apply_runtime_resilience

__all__ = ["apply_runtime_resilience"]
