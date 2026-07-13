from __future__ import annotations

from typing import Any

from .build import BuildPipeline
from ..state.repo import StateRepo
from ..state.verdict_store import get_records_for_governed_build


class _GovernedRepoProxy(StateRepo):
    """Immutable policy-aware StateRepo facade used by one build route."""

    def __init__(
        self,
        repo: StateRepo,
        *,
        publication_tier: