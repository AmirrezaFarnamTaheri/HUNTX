"""Core orchestration package."""

from .runtime_resilience import apply_runtime_resilience

apply_runtime_resilience()

__all__ = ["apply_runtime_resilience"]
