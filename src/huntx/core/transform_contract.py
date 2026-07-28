from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from .hardened_orchestrator import HardenedOrchestrator


class _TransformIncomplete(RuntimeError):
    def __init__(self, summary: dict[str, Any]):
        self.summary = summary
        super().__init__(f"transform stopped before drain: {summary.get('stop_reason', 'unknown')}")


def install_transform_contract() -> None:
    """Bind transform execution to the orchestrator's remaining deadline.

    ``HardenedOrchestrator`` historically called ``process_pending()`` without
    passing the run deadline and discarded the structured transform result. The
    wrapper preserves the public class and call graph while enforcing the
    bounded contract for every legacy and optimized caller.
    """

    orchestrator_type = HardenedOrchestrator
    if getattr(orchestrator_type, "_transform_contract_applied", False):
        return

    original: Callable[..., Awaitable[dict[str, Any]]] = orchestrator_type._run_hardened

    async def wrapped(
        self: HardenedOrchestrator,
        timeout: float | None,
        no_publish: bool,
        allow_partial_export: bool,
    ) -> dict[str, Any]:
        pipeline = self.transform_pipeline
        process_pending = pipeline.process_pending
        transform_summary: dict[str, Any] | None = None
        deadline_monotonic = None if timeout is None else time.monotonic() + max(0.0, timeout)

        def bounded_process_pending(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal transform_summary
            kwargs.setdefault("deadline_monotonic", deadline_monotonic)
            transform_summary = process_pending(*args, **kwargs)
            if not bool(transform_summary.get("completed")):
                raise _TransformIncomplete(transform_summary)
            return transform_summary

        setattr(pipeline, "process_pending", bounded_process_pending)
        try:
            summary = await original(self, timeout, no_publish, allow_partial_export)
        finally:
            setattr(pipeline, "process_pending", process_pending)

        if transform_summary is None:
            return summary

        summary["transform"] = transform_summary
        if bool(transform_summary.get("completed")):
            return summary

        reason = str(transform_summary.get("stop_reason") or "unknown")
        if reason == "deadline":
            summary["status"] = "timed_out"
            summary["timed_out"] = True
            summary["timed_out_stage"] = "transformation"
        else:
            summary["status"] = "partial"
            summary["timed_out"] = False
            summary["partial_reason"] = f"transform_{reason}"
        return summary

    orchestrator_type._run_hardened = wrapped  # type: ignore[method-assign]
    orchestrator_type._transform_contract_applied = True  # type: ignore[attr-defined]
