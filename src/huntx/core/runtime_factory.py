from __future__ import annotations

import logging
from typing import Any, Optional

from ..config.schema import AppConfig
from ..pipeline.governed_build import GovernedBuildPipeline
from ..state.consumer_reconciliation import reconcile_configured_bot_consumers
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .runtime_resilience import apply_runtime_resilience

logger = logging.getLogger(__name__)


def create_production_orchestrator(
    config: AppConfig,
    *,
    max_workers: int = 3,
    fetch_windows: Optional[dict[str, Any]] = None,
) -> OptimizedHardenedOrchestrator:
    """Construct the single governed production orchestration stack.

    Every production trigger must use this factory. Centralizing construction
    prevents CLI, bot-admin and future entry points from silently diverging on
    persistent-window ingestion, source governance, publication tiers, fresh
    probe requirements, manifest trust revocation, or Telegram consumer
    reconciliation.
    """
    apply_runtime_resilience()
    orchestrator = OptimizedHardenedOrchestrator(
        config,
        max_workers=max(1, int(max_workers)),
        fetch_windows=fetch_windows,
    )
    reconciliation = reconcile_configured_bot_consumers(orchestrator.repo, config)
    logger.info("Telegram consumer reconciliation: %s", reconciliation)

    route_policies = {
        route.name: (
            route.publication_tier.value,
            route.effective_require_fresh_probe,
        )
        for route in config.routes
    }
    orchestrator.build_pipeline = GovernedBuildPipeline(
        orchestrator.repo,
        orchestrator.artifact_store,
        orchestrator.registry,
        route_policies,
    )
    return orchestrator
