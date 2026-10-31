from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid
from typing import Any, Optional

from .hardened_orchestrator import HardenedOrchestrator
from .source_reliability import prioritize_http_sources, summarize_http_source_reports
from ..connectors.telegram_user.failure_policy import (
    is_permanent_telegram_peer_error,
    telegram_account_key,
    telegram_flood_wait_seconds,
)
from ..connectors.telegram_user.windowed import WindowedTelegramUserConnector
from ..pipeline.optimized_transform import OptimizedTransformPipeline
from ..pipeline.windowed_ingest import WindowedIngestionPipeline
from ..state.ingestion_queue import PersistentIngestionQueue

logger = logging.getLogger(__name__)


def _count_telegram_window_failure(results: dict[str, int], *, availability: bool) -> None:
    """Keep explicitly nonblocking upstream outages distinct from runtime defects."""
    if availability and os.environ.get("HUNTX_TELEGRAM_RETRY_RELEASE") == "1":
        results["optional_err"] = results.get("optional_err", 0) + 1
    else:
        results["err"] = results.get("err", 0) + 1


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a finite bounded floating-point environment setting."""
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        value = default
    if not math.isfinite(value):
        logger.warning("Non-finite %s=%r; using %s", name, raw, default)
        value = default
    return max(minimum, min(value, maximum))


def _canonical_timeout(self: Any) -> float:
    """Return the bounded Telegram canonical-channel resolution timeout."""
    return _bounded_float("HUNTX_CANONICAL_RESOLVE_TIMEOUT", 20.0, 0.05, 120.0)


def _cleanup_timeout(self: Any) -> float:
    """Return the bounded Telegram cleanup timeout."""
    return _bounded_float("HUNTX_TELEGRAM_CLEANUP_TIMEOUT", 10.0, 0.05, 60.0)


def _numeric_channel_id(peer: Any) -> Optional[int]:
    """Extract a canonical numeric Telegram channel ID when directly available."""
    text = str(peer).strip()
    if text.startswith("-100") and text[4:].isdigit():
        return int(text[4:])
    return None


async def _close_canonical_connector(
    self: Any,
    connector: Optional[WindowedTelegramUserConnector],
) -> None:
    """Close the reusable canonical-resolution connector within a bounded timeout."""
    if connector is None:
        return
    try:
        await asyncio.wait_for(
            connector.__aexit__(None, None, None),
            timeout=_cleanup_timeout(self),
        )
    except asyncio.TimeoutError:
        logger.error("[LIFO] Timed out closing canonical Telegram client")
    except Exception:
        logger.exception("[LIFO] Failed closing canonical Telegram client")


async def _canonical_ingestion_sources(
    self: Any,
    sources: list[Any],
) -> list[Any]:
    """Return reachable, canonicalized Telegram sources plus direct sources."""
    accepted: list[Any] = []
    canonical_owner: dict[int, str] = {}
    connector: Optional[WindowedTelegramUserConnector] = None
    connector_key: Optional[tuple[int, str, str]] = None
    flood_accounts: set[tuple[str, str, str]] = set()
    self._preflight_flood_deadlines = {}

    def defer_flood_wait(source: Any, exc: BaseException) -> bool:
        seconds = telegram_flood_wait_seconds(exc)
        if seconds is None:
            return False
        account = telegram_account_key(source)
        related = [
            str(candidate.id) for candidate in sources
            if account is not None and telegram_account_key(candidate) == account
        ] if account is not None else [str(source.id)]
        if account is not None:
            flood_accounts.add(account)
            self._preflight_flood_deadlines[account] = time.time() + seconds + 5
        postponed = self._work_queue.defer_sources(
            related,
            retry_delay=seconds + 5,
            reason="Telegram shared FloodWait cooldown",
        )
        logger.warning(
            "[LIFO] MTProto canonical preflight rate-limited for %ds; "
            "postponed %d already queued window(s), skipped further "
            "lookups for %d source(s) on the same account",
            seconds + 5, postponed, len(related),
        )
        return True

    try:
        for source in sources:
            if getattr(source, "type", None) != "telegram_user":
                accepted.append(source)
                continue

            config = getattr(source, "telegram_user", None)
            if config is None:
                self._work_queue.terminalize_source(
                    str(source.id),
                    "source is no longer configured as telegram_user",
                )
                continue

            if telegram_account_key(source) in flood_accounts:
                accepted.append(source)
                continue

            configured_channel_id = _numeric_channel_id(config.peer)
            if configured_channel_id is not None:
                existing = canonical_owner.get(configured_channel_id)
                if existing is not None:
                    reason = (
                        f"duplicate canonical Telegram channel {configured_channel_id}; "
                        f"owned by {existing}"
                    )
                    terminalized = self._work_queue.terminalize_source(
                        str(source.id),
                        reason,
                    )
                    logger.warning(
                        "[LIFO] Skipping numeric alias source %s for canonical "
                        "channel %s already owned by %s; terminalized=%s",
                        source.id,
                        configured_channel_id,
                        existing,
                        terminalized,
                    )
                    continue

            stop = getattr(self, "_ingestion_stop_monotonic", None)
            remaining = None if stop is None else stop - time.monotonic()
            if remaining is not None and remaining <= 0:
                self._ingestion_budget_exhausted = True
                accepted.append(source)
                continue

            operation_timeout = _canonical_timeout(self)
            if remaining is not None:
                operation_timeout = max(0.01, min(operation_timeout, remaining))

            key = (int(config.api_id), str(config.api_hash), str(config.session))
            if connector is None or connector_key != key:
                await _close_canonical_connector(self, connector)
                connector_class = WindowedTelegramUserConnector
                connector = connector_class(
                    api_id=config.api_id,
                    api_hash=config.api_hash,
                    session=config.session,
                    peer=config.peer,
                    state=None,
                    fetch_windows=None,
                )
                connector_key = key
                try:
                    await asyncio.wait_for(
                        connector.__aenter__(),
                        timeout=operation_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "[LIFO] Timed out acquiring Telegram session for %s; preserving source",
                        source.id,
                    )
                    connector = None
                    connector_key = None
                    accepted.append(source)
                    continue
                except Exception as exc:
                    if not defer_flood_wait(source, exc):
                        logger.exception(
                            "[LIFO] Failed acquiring Telegram session for %s; preserving source",
                            source.id,
                        )
                    connector = None
                    connector_key = None
                    accepted.append(source)
                    continue

            connector.peer = config.peer
            try:
                resolver = getattr(
                    connector,
                    "resolve_channel_id_strict_async",
                    connector.resolve_channel_id_async,
                )
                resolved_channel_id = await asyncio.wait_for(
                    resolver(),
                    timeout=operation_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[LIFO] Canonical resolution timed out for %s after %.2fs; preserving source",
                    source.id,
                    operation_timeout,
                )
                await _close_canonical_connector(self, connector)
                connector = None
                connector_key = None
                accepted.append(source)
                continue
            except Exception as exc:
                if defer_flood_wait(source, exc):
                    await _close_canonical_connector(self, connector)
                    connector = None
                    connector_key = None
                    accepted.append(source)
                    continue
                if is_permanent_telegram_peer_error(exc):
                    reason = (
                        "permanent Telegram peer failure during canonical preflight: "
                        f"{type(exc).__name__}"
                    )
                    terminalized = self._work_queue.terminalize_source(
                        str(source.id),
                        reason,
                    )
                    logger.warning(
                        "[LIFO] Excluding permanently unavailable Telegram source=%s "
                        "type=%s terminalized=%s",
                        source.id,
                        type(exc).__name__,
                        terminalized,
                    )
                    continue

                logger.exception(
                    "[LIFO] Could not resolve canonical channel for %s; preserving source",
                    source.id,
                )
                await _close_canonical_connector(self, connector)
                connector = None
                connector_key = None
                accepted.append(source)
                continue

            if resolved_channel_id is None and configured_channel_id is not None:
                reason = "numeric Telegram peer is unreachable with the configured session"
                terminalized = self._work_queue.terminalize_source(
                    str(source.id),
                    reason,
                )
                logger.warning(
                    "[LIFO] Excluding unreachable numeric Telegram source=%s "
                    "channel=%s terminalized=%s",
                    source.id,
                    configured_channel_id,
                    terminalized,
                )
                continue

            channel_id = (
                int(resolved_channel_id)
                if resolved_channel_id is not None
                else configured_channel_id
            )
            if channel_id is None:
                accepted.append(source)
                continue

            existing = canonical_owner.get(int(channel_id))
            if existing is None:
                canonical_owner[int(channel_id)] = str(source.id)
                accepted.append(source)
                continue

            reason = f"duplicate canonical Telegram channel {channel_id}; owned by {existing}"
            terminalized = self._work_queue.terminalize_source(str(source.id), reason)
            logger.warning(
                "[LIFO] Skipping alias source %s for canonical channel %s already owned by %s; terminalized=%s",
                source.id,
                channel_id,
                existing,
                terminalized,
            )
    finally:
        await _close_canonical_connector(self, connector)

    return accepted


async def _run_hardened(
    self: Any,
    timeout: Optional[float],
    no_publish: bool,
    allow_partial_export: bool,
) -> dict[str, Any]:
    """Run the resilient optimized pipeline without bypassing source trust policy."""
    run_started = time.monotonic()
    original = list(self.config.sources)
    approved = [
        source
        for source in original
        if getattr(source, "publication_eligible", True)
    ]
    rejected = [
        source
        for source in original
        if not getattr(source, "publication_eligible", True)
    ]
    for source in rejected:
        terminalized = self._work_queue.terminalize_source(
            str(source.id),
            "source is not publication-approved",
        )
        if terminalized:
            logger.warning(
                "[LIFO] Terminalized %s queued work item(s) for unapproved source %s",
                terminalized,
                source.id,
            )

    self._ingestion_budget_exhausted = False
    self._window_pages = 0
    self._window_completions = 0
    self._window_failures = 0
    self._reset_investigation_metrics()
    # The resilient override must initialize the ledger used by both direct
    # HTTP success and failure paths; without it reports silently disappear.
    self._http_source_reports = {}
    self._run_owner = uuid.uuid4().hex
    self._completion_buffer_seconds = self._completion_buffer(timeout)

    if timeout is not None:
        ingestion_budget = max(0.0, timeout - self._completion_buffer_seconds)
        self._ingestion_stop_monotonic = run_started + ingestion_budget
    else:
        ingestion_budget = None
        self._ingestion_stop_monotonic = None

    seed: dict[str, int] = {
        "campaign_id": 0,
        "anchor_ts": 0,
        "target_start_ts": 0,
        "inserted": 0,
    }
    preflight_seconds = 0.0
    summary: dict[str, Any]
    ingestion_sources: list[Any] = []
    try:
        recovered = self._work_queue.recover_expired_leases()
        ingestion_sources = await self._canonical_ingestion_sources(approved)
        # Stable, source-scoped historical retrieval evidence ranks optional
        # public feeds without ever reordering canonical Telegram windows.
        http_ids = [
            str(source.id) for source in ingestion_sources
            if getattr(source, "type", None) == "http_subscription"
        ]
        if http_ids:
            state_loader = getattr(getattr(self, "repo", None), "get_source_states_batch", None)
            if callable(state_loader):
                states = state_loader(http_ids)
                ingestion_sources = prioritize_http_sources(ingestion_sources, states)
        self._source_by_id = {str(source.id): source for source in ingestion_sources}
        worker_count = min(getattr(self, "max_workers", 1), len(ingestion_sources))
        has_telegram_windows = any(
            getattr(source, "type", None) == "telegram_user"
            for source in ingestion_sources
        )
        self._window_worker_claimed = False
        self._windows_need_reserved_worker = has_telegram_windows and worker_count > 1
        self._single_worker_parallel_windows = has_telegram_windows and worker_count == 1
        self.config.sources = ingestion_sources
        seed = self._work_queue.seed_rolling_horizon(
            ingestion_sources,
            lookback_seconds=self._lookback_seconds(),
            window_seconds=self._window_seconds(),
        )
        # The flood may have happened before this run inserted new windows.
        # Apply its persisted deadline to those new rows as well.
        for account, deadline in getattr(self, "_preflight_flood_deadlines", {}).items():
            related = [
                str(source.id) for source in ingestion_sources
                if telegram_account_key(source) == account
            ]
            if related:
                self._work_queue.defer_sources(
                    related,
                    retry_delay=max(1, math.ceil(deadline - time.time())),
                    reason="Telegram shared FloodWait cooldown",
                )
        preflight_seconds = time.monotonic() - run_started
        remaining_total = None if timeout is None else max(0.0, timeout - preflight_seconds)
        logger.info(
            "[Orchestrator] budgets total=%s remaining_after_preflight=%s ingestion=%s "
            "completion_buffer=%s preflight_seconds=%.3f lifo_campaign=%s seeded=%s "
            "recovered_leases=%s approved=%s rejected=%s canonical=%s",
            timeout,
            remaining_total,
            ingestion_budget,
            self._completion_buffer_seconds,
            preflight_seconds,
            seed["campaign_id"],
            seed["inserted"],
            recovered,
            len(approved),
            len(rejected),
            len(ingestion_sources),
        )
        summary = await HardenedOrchestrator._run_hardened(
            self,
            remaining_total,
            no_publish,
            allow_partial_export,
        )
    finally:
        try:
            windowed = getattr(self, "_windowed_ingestion", None)
            if windowed is not None:
                await windowed.close(_cleanup_timeout(self))
        finally:
            try:
                released = self._work_queue.release_owner(self._run_owner)
                if released:
                    logger.warning("[LIFO] Released %s unfinished lease(s) to residue", released)
            finally:
                self.config.sources = original
                self._source_by_id = {str(source.id): source for source in original}
                self._ingestion_stop_monotonic = None

    residue = self._work_queue.summary()
    remaining_residue = int(residue.get("remaining", 0))
    summary["duration_seconds"] = float(summary.get("duration_seconds", 0.0)) + preflight_seconds
    summary["preflight_seconds"] = preflight_seconds
    summary["completion_buffer_seconds"] = self._completion_buffer_seconds
    summary["ingestion_budget_seconds"] = ingestion_budget
    summary["ingestion_budget_exhausted"] = self._ingestion_budget_exhausted
    summary["lifo_campaign_id"] = seed["campaign_id"]
    summary["lifo_anchor_ts"] = seed["anchor_ts"]
    summary["lifo_target_start_ts"] = seed["target_start_ts"]
    summary["lifo_windows_seeded"] = seed["inserted"]
    summary["lifo_pages_processed"] = self._window_pages
    summary["lifo_windows_completed"] = self._window_completions
    summary["lifo_window_failures"] = self._window_failures
    summary["lifo_residue"] = residue
    summary.update(self._investigation_metrics())
    summary.update(summarize_http_source_reports(self._http_source_reports))
    summary["ingest_skipped_due_to_budget"] = (
        remaining_residue if self._ingestion_budget_exhausted else 0
    )
    summary["configured_approved_sources"] = len(approved)
    summary["excluded_sources"] = len(rejected)
    summary["canonical_ingestion_sources"] = len(ingestion_sources)

    retry_only_release = OptimizedHardenedOrchestrator._telegram_retry_release_allowed(self, residue)
    summary["telegram_availability_degraded"] = retry_only_release
    summary["telegram_retry_windows"] = int(residue.get("retry_wait", 0))
    if retry_only_release:
        logger.warning(
            "[LIFO] Telegram availability degraded: %d retrying windows; "
            "current authenticated HTTP release path remains independently gated",
            remaining_residue,
        )
    if self._ingestion_budget_exhausted and summary.get("status") == "completed":
        summary["status"] = "partial"
    if self._ingestion_budget_exhausted:
        summary["partial_reason"] = "ingestion_budget_exhausted"
    elif remaining_residue > 0 and not retry_only_release and summary.get("status") == "completed":
        summary["status"] = "partial"
        summary["partial_reason"] = "ingestion_residue_remaining"
    if summary.get("status") != "completed":
        # A demoted status can no longer authorize replacing the release.
        summary["release_eligible"] = False

    logger.info("[Orchestrator] optimized final summary=%s", summary)
    return summary


class OptimizedHardenedOrchestrator(HardenedOrchestrator):
    """Hardened runner with persistent newest-window-first ingestion."""

    _canonical_timeout = _canonical_timeout
    _cleanup_timeout = _cleanup_timeout
    _numeric_channel_id = staticmethod(_numeric_channel_id)
    _close_canonical_connector = _close_canonical_connector
    _canonical_ingestion_sources = _canonical_ingestion_sources
    _run_hardened = _run_hardened

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.transform_pipeline = OptimizedTransformPipeline(
            self.raw_store,
            self.repo,
            self.registry,
            {source.id: source for source in self.config.sources},
            max_workers=self.max_workers,
        )
        self._source_by_id = {str(source.id): source for source in self.config.sources}
        self._work_queue = PersistentIngestionQueue(self.db)
        self._windowed_ingestion = WindowedIngestionPipeline(
            self.ingest_pipeline,
            self._work_queue,
        )
        self._ingestion_stop_monotonic: Optional[float] = None
        self._ingestion_budget_exhausted = False
        self._completion_buffer_seconds = 0.0
        self._run_owner = ""
        self._preflight_flood_deadlines: dict[tuple[str, str, str], float] = {}
        self._window_pages = 0
        self._window_completions = 0
        self._window_failures = 0
        self._sources_checked: set[str] = set()
        self._messages_scanned = 0
        self._messages_new = 0
        self._cursor_updates = 0

    def _source_timeout(self) -> float:
        raw = os.environ.get("HUNTX_SOURCE_TIMEOUT", "600")
        try:
            return max(30.0, min(float(raw), 1800.0))
        except ValueError:
            logger.warning("Invalid HUNTX_SOURCE_TIMEOUT=%r; using 600", raw)
            return 600.0

    def _completion_buffer(self, timeout: Optional[float]) -> float:
        if timeout is None or timeout <= 0:
            return 0.0
        raw = os.environ.get("HUNTX_COMPLETION_BUFFER", "1800")
        try:
            requested = float(raw)
        except ValueError:
            logger.warning("Invalid HUNTX_COMPLETION_BUFFER=%r; using 1800", raw)
            requested = 1800.0
        return max(0.0, min(requested, max(0.0, timeout - 60.0)))

    def _window_seconds(self) -> int:
        raw = os.environ.get("HUNTX_INGEST_WINDOW_SECONDS", "3600")
        try:
            return max(300, min(int(raw), 24 * 3600))
        except ValueError:
            logger.warning("Invalid HUNTX_INGEST_WINDOW_SECONDS=%r; using 3600", raw)
            return 3600

    def _window_page_size(self) -> int:
        raw = os.environ.get("HUNTX_INGEST_PAGE_SIZE", "100")
        try:
            return max(10, min(int(raw), 1000))
        except ValueError:
            logger.warning("Invalid HUNTX_INGEST_PAGE_SIZE=%r; using 100", raw)
            return 100

    @staticmethod
    def _bounded_lookback_hours(value: Any) -> Optional[int]:
        try:
            hours = float(value)
            if not math.isfinite(hours):
                return None
            return max(3600, min(int(hours * 3600), 30 * 24 * 3600))
        except (OverflowError, TypeError, ValueError):
            return None

    def _lookback_seconds(self) -> int:
        raw = os.environ.get("HUNTX_LIFO_LOOKBACK_HOURS", "").strip()
        if raw:
            parsed = self._bounded_lookback_hours(raw)
            if parsed is not None:
                return parsed
            logger.warning("Invalid HUNTX_LIFO_LOOKBACK_HOURS=%r", raw)

        configured = self.fetch_windows.get("file_fresh_hours", 48) or 48
        parsed = self._bounded_lookback_hours(configured)
        if parsed is not None:
            return parsed
        logger.warning("Invalid file_fresh_hours=%r; using 48", configured)
        return 48 * 3600

    def _remaining_ingestion_budget(self) -> Optional[float]:
        stop = self._ingestion_stop_monotonic
        if stop is None:
            return None
        return stop - time.monotonic()

    def _telegram_retry_release_allowed(self, residue: dict[str, Any]) -> bool:
        """Permit current verified HTTP output when Telegram is only retry-waiting.

        Retry-only status is an availability problem, not a completed Telegram
        scan. We still require a current parsed HTTP feed with real nodes, an
        explicit production opt-in, and no exhausted ingestion budget. Other
        incomplete work, missing state, and missing HTTP evidence fail closed.
        The separate authenticated proxy-health/release receipt remains required.
        """
        if os.environ.get("HUNTX_TELEGRAM_RETRY_RELEASE") != "1":
            return False
        if getattr(self, "_ingestion_budget_exhausted", False):
            return False
        remaining = residue.get("remaining")
        retry_wait = residue.get("retry_wait")
        if (type(remaining) is not int or type(retry_wait) is not int
                or remaining <= 0 or retry_wait != remaining):
            return False
        reports = getattr(self, "_http_source_reports", None)
        if not isinstance(reports, dict):
            return False
        return any(
            isinstance(report, dict)
            and report.get("status") in {"parsed", "audited"}
            and type(report.get("nodes")) is int
            and report["nodes"] > 0
            for report in reports.values()
        )

    def _ingestion_demotion_reason(self) -> Optional[str]:
        """Fail closed except for explicitly allowed, retry-only Telegram outages."""
        if getattr(self, "_ingestion_budget_exhausted", False):
            return "ingestion_budget_exhausted"
        queue = getattr(self, "_work_queue", None)
        if queue is None:
            return "ingestion_state_unavailable"
        try:
            residue = queue.summary()
            if not isinstance(residue, dict):
                raise ValueError("unexpected ingestion queue summary")
            remaining = residue.get("remaining")
            if type(remaining) is not int or remaining < 0:
                raise ValueError("invalid ingestion queue remaining count")
        except Exception:
            logger.exception("[LIFO] Ingestion queue state cannot be verified")
            return "ingestion_state_unavailable"
        if remaining > 0 and not self._telegram_retry_release_allowed(residue):
            return "ingestion_residue_remaining"
        return None

    def _reset_investigation_metrics(self) -> None:
        """Reset concrete ingestion-evidence counters for one run."""
        self._sources_checked = set()
        self._messages_scanned = 0
        self._messages_new = 0
        self._cursor_updates = 0

    def _investigation_metrics(self) -> dict[str, int]:
        """Return machine-readable evidence used by the investigation gate."""
        return {
            "sources_checked": len(self._sources_checked),
            "messages_scanned": int(self._messages_scanned),
            "messages_new": int(self._messages_new),
            "cursor_updates": int(self._cursor_updates),
        }

    async def _run_direct_source(
        self,
        source: Any,
        results: dict[str, int],
        lock: asyncio.Lock,
        configured_timeout: float,
    ) -> None:
        remaining = self._remaining_ingestion_budget()
        if remaining is not None and remaining <= 0:
            self._ingestion_budget_exhausted = True
            return
        timeout = configured_timeout if remaining is None else min(configured_timeout, remaining)
        success = False
        self._sources_checked.add(str(source.id))
        try:
            success = bool(
                await asyncio.wait_for(
                    self._ingest_one_source_async(source),
                    timeout=timeout,
                )
            )
        except asyncio.TimeoutError:
            if getattr(source, "type", None) == "http_subscription":
                self._record_http_source_failure(str(source.id), "TimeoutError")
            if remaining is not None and timeout < configured_timeout:
                self._ingestion_budget_exhausted = True
                logger.warning(
                    "[Worker] Ingestion budget reached while processing %s; continuing downstream",
                    source.id,
                )
            else:
                logger.error(
                    "[Worker] Source %s exceeded %.1fs and was isolated",
                    source.id,
                    timeout,
                )
        except Exception as exc:
            if getattr(source, "type", None) == "http_subscription":
                self._record_http_source_failure(str(source.id), type(exc).__name__)
            logger.error("[Worker] Source %s failed error_type=%s", source.id, type(exc).__name__)
        finally:
            async with lock:
                if success:
                    results["ok"] += 1
                elif getattr(source, "required", True):
                    results["err"] += 1
                else:
                    results["optional_err"] = results.get("optional_err", 0) + 1

    async def _run_persistent_windows(
        self,
        results: dict[str, int],
        lock: asyncio.Lock,
        configured_timeout: float,
    ) -> None:
        page_size = self._window_page_size()
        lease_seconds = int(configured_timeout) + 60

        while True:
            remaining = self._remaining_ingestion_budget()
            if remaining is not None and remaining <= 0:
                self._ingestion_budget_exhausted = True
                return

            item = self._work_queue.claim_next(
                self._run_owner,
                lease_seconds=lease_seconds,
            )
            if item is None:
                return

            source = self._source_by_id.get(item.source_id)
            if source is None or getattr(source, "telegram_user", None) is None:
                self._window_failures += 1
                self._work_queue.mark_terminal(
                    item.id,
                    self._run_owner,
                    f"source configuration {item.source_id!r} is unavailable or unapproved",
                    lease_token=item.lease_token,
                )
                async with lock:
                    results["err"] += 1
                continue

            self._sources_checked.add(str(item.source_id))
            timeout = configured_timeout if remaining is None else min(configured_timeout, remaining)
            wall_deadline = time.time() + timeout
            try:
                page_result = await asyncio.wait_for(
                    self._windowed_ingestion.run_page(
                        source,
                        item,
                        owner=self._run_owner,
                        deadline=wall_deadline,
                        page_size=page_size,
                    ),
                    timeout=timeout,
                )
                self._window_pages += 1
                self._messages_scanned += max(0, int(page_result["scanned_messages"] or 0))
                self._messages_new += max(0, int(page_result["items_ingested"] or 0))
                # A successful page always checkpoints either a continuation
                # cursor or terminal completion in the same DB transaction as
                # its newly ingested observations.
                self._cursor_updates += 1
                if bool(page_result["completed"]):
                    self._window_completions += 1
                    async with lock:
                        results["ok"] += 1
                logger.info(
                    "[LIFO] source=%s window=[%s,%s) scanned=%s ingested=%s "
                    "cursor=%s completed=%s",
                    item.source_id,
                    item.window_start_ts,
                    item.window_end_ts,
                    page_result["scanned_messages"],
                    page_result["items_ingested"],
                    page_result["continuation_cursor"],
                    page_result["completed"],
                )
            except asyncio.TimeoutError:
                self._window_failures += 1
                retry_delay = (
                    1 if remaining is not None and timeout < configured_timeout else 60
                )
                self._work_queue.fail(
                    item.id,
                    self._run_owner,
                    "window page timed out",
                    lease_token=item.lease_token,
                    retry_delay=retry_delay,
                )
                budget_ended = remaining is not None and timeout < configured_timeout
                if budget_ended:
                    self._ingestion_budget_exhausted = True
                async with lock:
                    _count_telegram_window_failure(results, availability=not budget_ended)
                if budget_ended:
                    return
            except Exception as exc:
                self._window_failures += 1
                flood_wait = telegram_flood_wait_seconds(exc)
                if flood_wait is not None:
                    # MTProto FloodWait is an account-level Retry-After, not
                    # hundreds of independent broken source windows. Preserve
                    # all cursors and postpone only peers using this session.
                    retry_delay = flood_wait + 5
                    account_key = telegram_account_key(source)
                    session_sources = (
                        [
                            source_id for source_id, candidate in self._source_by_id.items()
                            if telegram_account_key(candidate) == account_key
                        ]
                        if account_key is not None else [item.source_id]
                    )
                    self._work_queue.fail(
                        item.id,
                        self._run_owner,
                        "Telegram shared FloodWait cooldown",
                        lease_token=item.lease_token,
                        retry_delay=retry_delay,
                    )
                    postponed = self._work_queue.defer_sources(
                        session_sources,
                        retry_delay=retry_delay,
                        reason="Telegram shared FloodWait cooldown",
                    )
                    async with lock:
                        _count_telegram_window_failure(results, availability=True)
                    logger.warning(
                        "[LIFO] Telegram account rate-limited for %ds; deferred "
                        "%d queued window(s) for %d source(s), preserving cursors",
                        retry_delay,
                        postponed,
                        len(session_sources),
                    )
                    continue
                if is_permanent_telegram_peer_error(exc):
                    reason = (
                        "permanent Telegram peer failure: "
                        f"{type(exc).__name__}"
                    )
                    terminalized = self._work_queue.terminalize_source(
                        item.source_id,
                        reason,
                    )
                    async with lock:
                        _count_telegram_window_failure(results, availability=True)
                    logger.warning(
                        "[LIFO] Quarantined source=%s after permanent Telegram "
                        "peer failure type=%s terminalized=%s",
                        item.source_id,
                        type(exc).__name__,
                        terminalized,
                    )
                    continue

                retry_delay = min(3600, 2 ** min(item.attempt_count, 10))
                self._work_queue.fail(
                    item.id,
                    self._run_owner,
                    f"window error: {type(exc).__name__}",
                    lease_token=item.lease_token,
                    retry_delay=retry_delay,
                )
                async with lock:
                    results["err"] += 1
                logger.error(
                    "[LIFO] Window failed source=%s window=[%s,%s) error_type=%s",
                    item.source_id,
                    item.window_start_ts,
                    item.window_end_ts,
                    type(exc).__name__,
                )

    async def _drain_direct_sources(
        self,
        source_queue: asyncio.Queue[Any],
        results: dict[str, int],
        lock: asyncio.Lock,
        configured_timeout: float,
    ) -> None:
        while True:
            try:
                source = source_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                if getattr(source, "type", None) != "telegram_user":
                    await self._run_direct_source(
                        source, results, lock, configured_timeout,
                    )
            finally:
                source_queue.task_done()

    async def _worker_async(
        self,
        source_queue: asyncio.Queue[Any],
        results: dict[str, int],
        lock: asyncio.Lock,
    ) -> None:
        configured_timeout = self._source_timeout()
        if getattr(self, "_windows_need_reserved_worker", False):
            # An optional HTTP feed can occupy a worker for a full timeout.
            # Start MTProto history immediately, rather than waiting for
            # every direct source to finish before draining Telegram windows.
            # There are no awaits between checking and setting the claim.
            if not getattr(self, "_window_worker_claimed", False):
                self._window_worker_claimed = True
                await self._run_persistent_windows(results, lock, configured_timeout)
                return
        if getattr(self, "_single_worker_parallel_windows", False):
            if not getattr(self, "_window_worker_claimed", False):
                self._window_worker_claimed = True
                # A single worker would otherwise starve Telegram history.
                # Run exactly one bounded direct worker and one window worker.
                await asyncio.gather(
                    self._drain_direct_sources(
                        source_queue, results, lock, configured_timeout,
                    ),
                    self._run_persistent_windows(results, lock, configured_timeout),
                )
                return
        await self._drain_direct_sources(
            source_queue, results, lock, configured_timeout,
        )
        await self._run_persistent_windows(results, lock, configured_timeout)
