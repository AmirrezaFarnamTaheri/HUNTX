from __future__ import annotations

import concurrent.futures
import threading
from typing import Any

from .build import BuildPipeline
from ..state.repo import StateRepo
from ..state.verdict_store import get_records_for_governed_build

_RecordList = list[dict[str, Any]]
_QueryKey = tuple[str, bool, tuple[str, ...], tuple[str, ...], int | None]


class _GovernedRepoProxy(StateRepo):
    """Immutable policy-aware StateRepo facade used by one build route."""

    def __init__(
        self,
        repo: StateRepo,
        *,
        publication_tier: str,
        require_fresh_probe: bool,
    ) -> None:
        super().__init__(repo.db)
        self._publication_tier = publication_tier
        self._require_fresh_probe = require_fresh_probe

    def get_records_for_build(
        self,
        record_types: list[str],
        allowed_source_ids: list[str],
        min_seen_file_id: int | None = None,
    ) -> _RecordList:
        return get_records_for_governed_build(
            self.db,
            record_types,
            allowed_source_ids,
            min_seen_file_id=min_seen_file_id,
            publication_tier=self._publication_tier,
            require_fresh_probe=self._require_fresh_probe,
        )


class GovernedBuildPipeline(BuildPipeline):
    """Thread-safe governed build facade with query single-flight reuse.

    Equivalent concurrent routes share one governed database query. Handler locks
    remain shared because registry handlers are singleton instances and are not
    assumed to be re-entrant.
    """

    def __init__(
        self,
        state_repo: StateRepo,
        artifact_store: Any,
        registry: Any,
        route_policies: dict[str, tuple[str, bool]],
    ) -> None:
        super().__init__(state_repo, artifact_store, registry)
        self._route_policies = route_policies
        self._query_lock = threading.Lock()
        self._query_futures: dict[
            _QueryKey, concurrent.futures.Future[_RecordList]
        ] = {}

    @staticmethod
    def _query_key(
        tier: str,
        require_fresh_probe: bool,
        route_config: dict[str, Any],
    ) -> _QueryKey:
        formats = tuple(sorted({str(value) for value in route_config["formats"]}))
        sources = tuple(
            sorted({str(value) for value in route_config.get("from_sources", [])})
        )
        min_seen_file_id = route_config.get("min_seen_file_id")
        return tier, require_fresh_probe, formats, sources, min_seen_file_id

    def _records_for_route(
        self,
        route_config: dict[str, Any],
        *,
        tier: str,
        require_fresh_probe: bool,
    ) -> _RecordList:
        key = self._query_key(tier, require_fresh_probe, route_config)
        owner = False
        with self._query_lock:
            future = self._query_futures.get(key)
            if future is None:
                future = concurrent.futures.Future()
                self._query_futures[key] = future
                owner = True

        if owner:
            try:
                proxy = _GovernedRepoProxy(
                    self.state_repo,
                    publication_tier=tier,
                    require_fresh_probe=require_fresh_probe,
                )
                records = proxy.get_records_for_build(
                    list(key[2]),
                    list(key[3]),
                    min_seen_file_id=key[4],
                )
                future.set_result(records)
            except BaseException as exc:
                future.set_exception(exc)
                with self._query_lock:
                    self._query_futures.pop(key, None)
                raise
        return future.result()

    def run(self, route_config: dict[str, Any]) -> list[dict[str, Any]]:
        route_name = str(route_config["name"])
        tier, require_fresh_probe = self._route_policies.get(
            route_name, ("compatible", False)
        )
        records = self._records_for_route(
            route_config,
            tier=tier,
            require_fresh_probe=require_fresh_probe,
        )
        route_pipeline = BuildPipeline(
            self.state_repo,
            self.artifact_store,
            self.registry,
            format_locks=self._format_locks,
            format_locks_guard=self._format_locks_guard,
        )
        return route_pipeline.run(route_config, records=records)
