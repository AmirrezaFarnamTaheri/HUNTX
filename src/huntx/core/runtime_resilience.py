"""Resilient runtime support for the governed production stack.

The resilient behaviour itself lives in ``optimized_orchestrator``:
``_run_hardened``, ``_canonical_ingestion_sources`` and the bounded timeout
helpers are bound as methods on ``OptimizedHardenedOrchestrator``, so every
construction path -- the runtime factory, the ``UnifiedOrchestrator`` facade
and a direct instantiation -- gets the same contract without anyone having to
install a patch first.

This module keeps the governed wiring that cannot live on the class:

  * the transform deadline contract, which wraps ``HardenedOrchestrator``;
  * the dev-manifest trust-revocation contract, which wraps ``Orchestrator``;
  * the fail-closed guard on the obsolete legacy orchestration entry point.

The strict Telegram peer-resolution seam that the preflight uses to tell a
permanent peer failure from a transient lookup error is a real method on
``TelegramUserConnector`` (``resolve_channel_id_strict_async``), not a patch
installed here, so it does not depend on this module having been imported.

The module-level names ``_run_hardened``, ``_canonical_ingestion_sources`` and
friends are aliases for the same implementations the class uses, so existing
callers and tests that reference them keep working.
"""
from __future__ import annotations

import logging
from typing import Any

from . import optimized_orchestrator as optimized_module
from .dev_manifest_contract import install_dev_manifest_contract
from .optimized_orchestrator import OptimizedHardenedOrchestrator
from .orchestrator import Orchestrator
from .transform_contract import install_transform_contract

logger = logging.getLogger(__name__)

install_transform_contract()
install_dev_manifest_contract(Orchestrator)


async def _disabled_legacy_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Fail closed if obsolete direct legacy orchestration is invoked."""
    raise RuntimeError(
        "_run_async_legacy is disabled; use run()/_run_async() through the hardened runtime"
    )


# Module-level aliases for the resilient behaviour the class now owns. They are
# the same functions the class binds, not copies: changing one changes the
# other. The implementations take ``self`` as their first argument, so the
# aliases stay callable with any object that implements the contract.
_canonical_timeout = optimized_module._canonical_timeout
_cleanup_timeout = optimized_module._cleanup_timeout
_numeric_channel_id = optimized_module._numeric_channel_id
_close_canonical_connector = optimized_module._close_canonical_connector
_canonical_ingestion_sources = optimized_module._canonical_ingestion_sources
_run_hardened = optimized_module._run_hardened

# Public spellings for callers that prefer them.
canonical_ingestion_sources = optimized_module._canonical_ingestion_sources
run_hardened = optimized_module._run_hardened


def apply_runtime_resilience() -> None:
    """Install the governed runtime contracts exactly once.

    The resilient run and preflight behaviour no longer needs installing: it
    is part of ``OptimizedHardenedOrchestrator`` itself. What remains here is
    the wiring that wraps other classes, and the fail-closed guard on the
    obsolete legacy entry point. Both are idempotent.
    """
    if getattr(Orchestrator, "_runtime_resilience_applied", False):
        return
    Orchestrator._run_async_legacy = _disabled_legacy_run  # type: ignore[method-assign]
    Orchestrator._runtime_resilience_applied = True  # type: ignore[attr-defined]
    OptimizedHardenedOrchestrator._runtime_resilience_applied = True  # type: ignore[attr-defined]


# The legacy orchestration entry point is disabled at import time, not only
# after ``apply_runtime_resilience()`` runs: a caller that imports this module
# directly must not be able to reach the unguarded path.
Orchestrator._run_async_legacy = _disabled_legacy_run  # type: ignore[method-assign]
