"""Regression tests for the runtime-resilience refactor.

The resilient run and preflight behaviour used to be installed by patching
``OptimizedHardenedOrchestrator`` at import time. A class-level patch meant
that the behaviour depended on ``runtime_resilience`` having been imported:
construct the class directly and you got the unpatched base implementation,
with no error to explain the difference. The behaviour now lives on the class
itself, and ``runtime_resilience`` keeps module-level aliases for the callers
that use them.
"""
import asyncio
import unittest

from huntx.core import runtime_resilience
from huntx.core.hardened_orchestrator import HardenedOrchestrator
from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


class TestRuntimeResilienceOwnership(unittest.TestCase):
    """The resilient behaviour is owned by the class, not by a patch."""

    def test_class_owns_the_resilient_methods(self):
        for name in (
            "_run_hardened",
            "_canonical_ingestion_sources",
            "_canonical_timeout",
            "_cleanup_timeout",
            "_numeric_channel_id",
            "_close_canonical_connector",
        ):
            self.assertIn(
                name,
                vars(OptimizedHardenedOrchestrator),
                f"{name} is not owned by OptimizedHardenedOrchestrator",
            )

    def test_class_methods_are_not_the_base_implementation(self):
        """The resilient run must not be the inherited hardened run."""
        self.assertIsNot(
            OptimizedHardenedOrchestrator._run_hardened,
            HardenedOrchestrator._run_hardened,
        )

    def test_module_aliases_are_the_same_objects(self):
        """The module names alias the class-bound functions, not copies."""
        self.assertIs(
            runtime_resilience._run_hardened,
            OptimizedHardenedOrchestrator._run_hardened,
        )
        self.assertIs(
            runtime_resilience._canonical_ingestion_sources,
            OptimizedHardenedOrchestrator._canonical_ingestion_sources,
        )

    def test_module_aliases_are_callable_with_a_duck_typed_self(self):
        """A caller that only implements the contract can still use them.

        The preflight used to be reachable only as a method of the patched
        class, so a caller holding any other object implementing the same
        contract had to install the patch itself first.
        """

        class Duck:
            def __init__(self):
                self._work_queue = _FakeQueue()
                self._ingestion_stop_monotonic = None

        duck = Duck()
        result = asyncio.run(
            runtime_resilience._canonical_ingestion_sources(duck, ["not-a-telegram-source"])
        )
        self.assertEqual(result, ["not-a-telegram-source"])

    def test_apply_runtime_resilience_is_idempotent(self):
        runtime_resilience.apply_runtime_resilience()
        first = Orchestrator._run_async_legacy
        runtime_resilience.apply_runtime_resilience()
        self.assertIs(Orchestrator._run_async_legacy, first)

    def test_legacy_entry_point_fails_closed(self):
        runtime_resilience.apply_runtime_resilience()
        with self.assertRaises(RuntimeError):
            asyncio.run(Orchestrator.__new__(Orchestrator)._run_async_legacy())


class _FakeQueue:
    """Minimal ingestion-queue stand-in for the preflight contract."""

    def __init__(self):
        self.terminalized = []

    def terminalize_source(self, source_id, reason):
        self.terminalized.append((source_id, reason))
        return 1


if __name__ == "__main__":
    unittest.main()
