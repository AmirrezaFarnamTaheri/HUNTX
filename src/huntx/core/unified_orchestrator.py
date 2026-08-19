from __future__ import annotations

from typing import Any

from .geo_routing import GeoRoutingEngine
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .resilience import AsyncCircuitBreaker
from .scoring import ProxyScoringEngine
from .self_healing import SelfHealingDaemon
from ..formats.streaming import StreamingChunkParser


class UnifiedOrchestrator(OptimizedHardenedOrchestrator):
    """Public next-generation facade backed by the production run contract.

    Historically this class maintained a separate execution graph that skipped
    ingestion and swallowed transformation failures.  A second orchestration
    path lets deadlines, source governance, persistence and publication policy
    drift from production.  The facade now inherits the optimized hardened
    pipeline and adds only its next-generation helper components/metadata.
    """

    def __init__(
        self,
        *args: Any,
        enable_benchmarking: bool = True,
        max_proxy_latency_ms: int = 1500,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.enable_benchmarking = bool(enable_benchmarking)
        self.max_proxy_latency_ms = max(1, int(max_proxy_latency_ms))
        self.circuit_breaker = AsyncCircuitBreaker()
        self.scoring_engine = ProxyScoringEngine()
        self.streaming_parser = StreamingChunkParser()
        self.geo_routing = GeoRoutingEngine()
        self.self_healing = SelfHealingDaemon()

    def run(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ) -> dict[str, Any]:
        """Run the canonical optimized/hardened pipeline and label the facade."""
        summary = dict(
            super().run(
                timeout=timeout,
                no_publish=no_publish,
                allow_partial_export=allow_partial_export,
            )
        )
        summary["unified"] = True
        summary["elapsed_seconds"] = float(summary.get("duration_seconds", 0.0))
        return summary
