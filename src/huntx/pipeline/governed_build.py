from __future__ import annotations

import concurrent.futures
import threading
from typing import Any, Optional

from .build import BuildPipeline
from ..core.deadline import Deadline, DeadlineExceeded
from ..state.repo import StateRepo
from ..state.verdict_store import get_records_for_governed_build

_RecordList = list[dict[str, Any]]
_QueryKey = tuple[str, bool, tuple[str, ...], tuple[str, ...], int | None, str | None]


class _GovernedRepoProxy(StateRepo):
    """Immutable policy-aware StateRepo facade used by one build route."""

    def __init__(
        self,
        repo: StateRepo,
        *,
        publication_tier: str,
        require_fresh_probe: bool,
        prefetched_records: Optional[_RecordList] = None,
    ) -> None:
        super().__init__(repo.db)
        self._publication_tier = publication_tier
        self._require_fresh_probe = require_fresh_probe
        self._prefetched_records = prefetched_records

    def get_records_for_build(
        self,
        record_types: list[str],
        allowed_source_ids: list[str],
        min_seen_file_id: Optional[int] = None,
        min_ingested_at: Optional[str] = None,
        deadline: Optional[Deadline] = None,
    ) -> list[dict[str, Any]]:
        if deadline is not None:
            deadline.raise_if_expired("governed build query")
        if self._prefetched_records is not None:
            # The caller already performed the policy-filtered, single-flight
            # query for this exact route. Leave records=None at BuildPipeline
            # so its historical scheduler still runs and writes true receipts.
            return list(self._prefetched_records)
        return get_records_for_governed_build(
            self.db,
            record_types,
            allowed_source_ids,
            min_seen_file_id=min_seen_file_id,
            min_ingested_at=min_ingested_at,
            publication_tier=self._publication_tier,
            require_fresh_probe=self._require_fresh_probe,
            **({"deadline": deadline} if deadline is not None else {}),
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
        self._query_futures: dict[_QueryKey, concurrent.futures.Future[_RecordList]] = {}

    @staticmethod
    def _query_key(
        tier: str,
        require_fresh_probe: bool,
        route_config: dict[str, Any],
    ) -> _QueryKey:
        formats = tuple(sorted({str(value) for value in route_config["formats"]}))
        sources = tuple(sorted({str(value) for value in route_config.get("from_sources", [])}))
        min_seen_file_id = route_config.get("min_seen_file_id")
        return tier, require_fresh_probe, formats, sources, min_seen_file_id, route_config.get("min_ingested_at")

    def _records_for_route(
        self,
        route_config: dict[str, Any],
        *,
        tier: str,
        require_fresh_probe: bool,
        deadline: Deadline | None = None,
    ) -> _RecordList:
        if deadline is not None:
            deadline.raise_if_expired("governed build query")
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
                    **({"min_ingested_at": key[5]} if key[5] is not None else {}),
                    **({"deadline": deadline} if deadline is not None else {}),
                )
                future.set_result(records)
            except Exception as exc:
                future.set_exception(exc)
                with self._query_lock:
                    self._query_futures.pop(key, None)
                raise
        if deadline is None:
            return future.result()
        try:
            return future.result(timeout=deadline.clamp_timeout(3600.0))
        except concurrent.futures.TimeoutError as exc:
            raise DeadlineExceeded(
                "Global deadline exhausted waiting for governed build query"
            ) from exc

    def run(  # type: ignore[override]
        self,
        route_config: dict[str, Any],
        *,
        records: Optional[list[dict[str, Any]]] = None,
        deadline: Deadline | None = None,
    ) -> list[dict[str, Any]]:
        if deadline is not None:
            deadline.raise_if_expired("build")
        route_repo: StateRepo = self.state_repo
        if records is None:
            route_name = str(route_config["name"])
            tier, require_fresh_probe = self._route_policies.get(route_name, ("compatible", False))
            records = self._records_for_route(
                route_config,
                tier=tier,
                require_fresh_probe=require_fresh_probe,
                deadline=deadline,
            )
            if route_name in {"all_sources", "all_sources_sub"}:
                # Real production uses GovernedBuildPipeline. Previously it
                # passed records= unconditionally, bypassing BuildPipeline's
                # source-independent historical retest selector. Retain the
                # single-flight governed query but let the canonical builder
                # obtain the prefetched fresh records through a StateRepo
                # facade, then schedule old genuine successes for NEW HTTPS.
                route_repo = _GovernedRepoProxy(
                    self.state_repo,
                    publication_tier=tier,
                    require_fresh_probe=require_fresh_probe,
                    prefetched_records=records,
                )
                records = None
        if deadline is not None:
            deadline.raise_if_expired("build")
        route_pipeline = BuildPipeline(
            route_repo,
            self.artifact_store,
            self.registry,
            format_locks=self._format_locks,
            format_locks_guard=self._format_locks_guard,
        )
        return route_pipeline.run(route_config, records=records, deadline=deadline)
