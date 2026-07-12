from __future__ import annotations

from typing import Any

from .build import BuildPipeline
from ..state.verdict_store import get_records_for_governed_build


class _GovernedRepoProxy:
    def __init__(
        self,
        repo: Any,
        *,
        publication_tier: str,
        require_fresh_probe: bool,
    ) -> None:
        self._repo = repo
        self._publication_tier = publication_tier
        self._require_fresh_probe = require_fresh_probe

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repo, name)

    def get_records_for_build(
        self,
        record_types: list[str],
        allowed_source_ids: list[str],
        min_seen_file_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return get_records_for_governed_build(
            self._repo.db,
            record_types,
            allowed_source_ids,
            min_seen_file_id=min_seen_file_id,
            publication_tier=self._publication_tier,
            require_fresh_probe=self._require_fresh_probe,
        )


class GovernedBuildPipeline(BuildPipeline):
    def __init__(
        self,
        state_repo: Any,
        artifact_store: Any,
        registry: Any,
        route_policies: dict[str, tuple[str, bool]],
    ) -> None:
        super().__init__(state_repo, artifact_store, registry)
        self._route_policies = route_policies

    def run(self, route_config: dict[str, Any]) -> list[dict[str, Any]]:
        route_name = str(route_config["name"])
        tier, require_fresh_probe = self._route_policies.get(
            route_name, ("compatible", False)
        )
        original_repo = self.state_repo
        self.state_repo = _GovernedRepoProxy(
            original_repo,
            publication_tier=tier,
            require_fresh_probe=require_fresh_probe,
        )
        try:
            return super().run(route_config)
        finally:
            self.state_repo = original_repo
