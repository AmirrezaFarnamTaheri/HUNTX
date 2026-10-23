import asyncio
import os
import concurrent.futures
import base64
import datetime
import json
import logging
import time
import threading
from pathlib import Path
from typing import Optional, Any
from ..connectors.base import run_sync
from ..store import paths
from ..store.raw_store import RawStore
from ..store.artifact_store import ArtifactStore
from ..state.db import open_db
from ..state.repo import StateRepo
from ..formats.registry import FormatRegistry
from ..formats.register_builtin import register_all_formats
from ..pipeline.ingest import IngestionPipeline
from ..pipeline.transform import TransformPipeline
from ..pipeline.build import BuildPipeline
from ..pipeline.publish import PublishPipeline
from ..formats.npvt import strip_proxy_remark, add_clean_remark
from ..config.schema import AppConfig
from ..utils.atomic import atomic_write
from ..connectors.base import maybe_await
from .output_ownership import output_filename
from .source_reliability import append_retrieval_observation, summarize_source_reliability

logger = logging.getLogger(__name__)

# Default number of parallel ingestion workers
DEFAULT_MAX_WORKERS = 3

# Minimum number of days to retain cumulative/cached output artifacts before
# a route-owned file that is no longer produced may be pruned.
DEFAULT_OUTPUT_RETENTION_DAYS = 3

# The proxy formats whose build also emits derivative products, and the
# suffixes of those products. The export layer must know them so it can tell a
# route-owned derivative apart from an unrelated file in the output directory.
_DERIVED_PROXY_FORMATS = frozenset({'npvt', 'npvtsub'})
_DERIVED_PROXY_SUFFIXES = (
    'decoded.json',
    'b64sub',
    'singbox.json',
    'xray.json',
    'nekobox.json',
    'clash.yaml',
    'singbox.profile.json',
    'xray.profile.json',
)
_LEGACY_OUTPUT_OWNERSHIP_MANIFEST = ".huntx-legacy-output-ownership.json"


class Orchestrator:

    # Retention window (days) for cumulative output artifacts in outputs/.
    OUTPUT_RETENTION_DAYS = DEFAULT_OUTPUT_RETENTION_DAYS

    def _output_retention_days(self) -> int:
        """Resolve the output retention window, honoring HUNTX_OUTPUT_RETENTION_DAYS.

        The environment variable overrides the class default when it parses to a
        non-negative integer; otherwise the class attribute is used.
        """
        raw = os.environ.get("HUNTX_OUTPUT_RETENTION_DAYS")
        if raw is not None:
            try:
                value = int(raw)
                if value >= 0:
                    return value
            except ValueError:
                pass
        return self.OUTPUT_RETENTION_DAYS

    def __init__(
        self,
        config: AppConfig,
        max_workers: int = DEFAULT_MAX_WORKERS,
        fetch_windows: Optional[dict] = None,
        runtime_paths: Optional[paths.RuntimePaths] = None,
    ):
        logger.info("[Orchestrator] Initializing...")
        self.config = config
        self.max_workers = max_workers
        self.fetch_windows = fetch_windows or {
            "msg_fresh_hours": 2,
            "file_fresh_hours": 48,
            "msg_subsequent_hours": 0,
            "file_subsequent_hours": 0,
        }
        self.paths = runtime_paths or paths.current_paths()

        self.raw_store = RawStore(self.paths.raw_store_dir)
        self.artifact_store = ArtifactStore(self.paths.data_dir)

        self.db = open_db(self.paths.state_db_path)
        self.repo = StateRepo(self.db)
        logger.debug(f"[Orchestrator] State DB at {self.paths.state_db_path}")

        # Optimization: Enable WAL mode for better concurrency (readers don't block writers)
        try:
            with self.db.connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
        except Exception as e:
            logger.warning(f"[Orchestrator] Could not set WAL mode: {e}")

        self.registry = FormatRegistry()
        register_all_formats(self.registry, self.raw_store)

        source_configs = {s.id: s for s in self.config.sources}

        self.ingest_pipeline = IngestionPipeline(self.raw_store, self.repo)
        self.transform_pipeline = TransformPipeline(
            self.raw_store, self.repo, self.registry, source_configs, max_workers=self.max_workers
        )
        self.build_pipeline = BuildPipeline(self.repo, self.artifact_store, self.registry)
        self.publish_pipeline = PublishPipeline(self.repo)
        self._seen_channels: set = set()  # canonical channel IDs for dedup
        self._seen_lock = threading.Lock()
        logger.info(
            f"[Orchestrator] Ready — {len(self.config.sources)} sources, "
            f"{len(self.config.routes)} routes, {self.max_workers} workers."
        )

    # ------------------------------------------------------------------
    # Output export
    # ------------------------------------------------------------------

    def _export_outputs(self, all_build_results: list):
        """Write this run's build artifacts to the registered output directory.
        These are committed back to the repo by CI."""
        out_dir = self.paths.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        # Collect payloads to write. Keyed by filename.
        output_payloads = {}

        for res in all_build_results:
            if not isinstance(res, dict):
                logger.warning(f"[Export] Ignoring malformed build result: {type(res).__name__}")
                continue
            route = res.get("route_name", "unknown")
            fmt = res.get("format", "unknown")
            data = res.get("data")
            if not data:
                continue

            filename = self._output_filename(route, fmt)
            output_payloads[filename] = data

        # Remove stale route files that are no longer part of expected naming.
        # Retention window: keep cumulative/cached artifacts for at least
        # OUTPUT_RETENTION_DAYS so a single run cannot wipe recently produced
        # output. Only files older than the window are pruned.
        #
        # Ownership is decided by exact filename, never by prefix. A prefix test
        # made route "all" own "all_sources.txt", so a run that stopped emitting
        # one route could delete a sibling route's artifact: "all_sources.txt" is
        # owned by route "all_sources", and "all_sources" is a prefix of it. The
        # set of filenames a route may own is computed from the same naming
        # contract that writes them, so a file is only ever considered stale if
        # it is an exact output name of a configured route and format.
        current_owners = {
            name: {"route": str(route.name), "format": str(fmt)}
            for route in self.config.routes
            for fmt in route.formats
            for name in self._owned_names_for_format(str(route.name), str(fmt))
        }
        # Persist route-scoped ownership because the active config cannot tell
        # us which format produced a stale artifact after that format is
        # removed. Only exact historical filenames recorded by this exporter
        # are eligible for retention cleanup.
        manifest_path = out_dir / _LEGACY_OUTPUT_OWNERSHIP_MANIFEST
        prior_owners: dict[str, dict[str, str]] = {}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and manifest.get("schema_version") == 1:
                files = manifest.get("files", {})
                if isinstance(files, dict):
                    for name, owner in files.items():
                        if (isinstance(name, str) and Path(name).name == name and isinstance(owner, dict)
                                and isinstance(owner.get("route"), str)
                                and isinstance(owner.get("format"), str)):
                            prior_owners[name] = {"route": owner["route"], "format": owner["format"]}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            logger.warning("[Export] Ignoring invalid legacy output ownership manifest")
        owned_filenames = set(prior_owners) | set(current_owners)
        retention_days = self._output_retention_days()
        retention_cutoff = time.time() - (retention_days * 86400)
        stale_removed = 0
        stale_retained = 0
        for existing in out_dir.iterdir():
            if not existing.is_file():
                continue
            # Skip non-pipeline files (README, scripts, etc.)
            name = existing.name
            if name not in owned_filenames:
                continue
            if name in output_payloads:
                continue
            # This is a route-owned file that is NOT in the new set → stale.
            # Retain it if younger than the retention window so outputs/ keeps
            # a rolling cumulative cache across runs.
            try:
                if existing.stat().st_mtime >= retention_cutoff:
                    stale_retained += 1
                    continue
            except OSError:
                pass
            try:
                existing.unlink()
                stale_removed += 1
                logger.info(f"[Export] Removed stale output: {name}")
            except OSError as e:
                logger.warning(f"[Export] Could not remove stale file {name}: {e}")
        if stale_removed:
            logger.info(f"[Export] Cleaned {stale_removed} stale file(s) from {out_dir}")
        if stale_retained:
            logger.info(
                f"[Export] Retained {stale_retained} cached file(s) within " f"{retention_days}-day window in {out_dir}"
            )

        # ── Write new outputs ─────────────────────────────────────────
        files_written = 0
        total_bytes = 0

        for filename, data in output_payloads.items():
            path = out_dir / filename
            try:
                if isinstance(data, bytes):
                    atomic_write(path, data)
                else:
                    atomic_write(path, str(data).encode("utf-8"))
                size = path.stat().st_size
                total_bytes += size
                files_written += 1
                logger.info(f"[Export] Written {filename} ({size / 1024:.1f} KB)")
            except Exception as e:
                logger.error(f"[Export] Failed to write {filename}: {e}")

        # Retain ownership for cached files still inside the retention window;
        # discard ownership only after a stale file has actually disappeared.
        next_owners = {**prior_owners, **current_owners}
        next_owners.update({name: current_owners.get(name, {"route": "unknown", "format": "unknown"})
                            for name in output_payloads})
        next_owners = {name: owner for name, owner in next_owners.items() if (out_dir / name).is_file()}
        atomic_write(manifest_path, json.dumps({"schema_version": 1, "files": next_owners},
                                               sort_keys=True).encode("utf-8"))

        if files_written == 0:
            logger.warning("[Export] No artifacts produced — outputs/ not updated.")
        else:
            logger.info(
                f"[Export] Exported {files_written} file(s) to {out_dir} " f"({total_bytes / 1024:.1f} KB total)"
            )

    def _owned_output_filenames(self) -> set[str]:
        """Return the exact set of filenames this configuration may own.

        A route owns the canonical name of every format it is configured to
        build, plus the derivative products the build pipeline derives from a
        proxy format. Ownership is by exact filename, so one route can never be
        treated as the owner of a sibling route's artifact just because the two
        names share a prefix.
        """
        owned: set[str] = set()
        for route in self.config.routes:
            route_name = str(route.name)
            for fmt in route.formats:
                owned.update(self._owned_names_for_format(route_name, str(fmt)))
        return owned

    def _owned_names_for_format(self, route_name: str, fmt: str) -> set[str]:
        owned = {self._output_filename(route_name, fmt)}
        if fmt in _DERIVED_PROXY_FORMATS:
            owned.update(self._output_filename(route_name, f"{fmt}.{suffix}")
                         for suffix in _DERIVED_PROXY_SUFFIXES)
        return owned

    @staticmethod
    def _output_filename(route: str, fmt: str) -> str:
        """Use the shared route/format naming contract."""
        return output_filename(route, fmt)

    # ------------------------------------------------------------------
    # Dev output export
    # ------------------------------------------------------------------

    def _export_dev_outputs(self, all_build_results: list):
        """Accumulate proxy URIs into the registered dev output directory as an all-time cumulative set.

        Writes three files from the accumulated state:
          - proxies.txt      — one URI per line
          - proxies.json     — structured JSON with metadata
          - proxies_b64sub.txt — base64-encoded subscription
        A hidden _manifest.json tracks {uri: first_seen_timestamp} for dedup
        across runs.
        """
        dev_dir = self.paths.dev_output_dir
        dev_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = dev_dir / "_manifest.json"
        now = time.time()

        # ── Load existing manifest ────────────────────────────────────
        manifest: dict = {}  # {uri_string: first_seen_epoch}
        if manifest_path.exists():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[DevExport] Could not read manifest, starting fresh: {e}")
            else:
                # Only numeric first_seen timestamps participate in dedup/sort;
                # anything else would crash the deterministic sort below.
                manifest = {
                    uri: seen
                    for uri, seen in loaded.items()
                    if isinstance(seen, (int, float)) and not isinstance(seen, bool)
                }
                if len(manifest) != len(loaded):
                    logger.warning("[DevExport] Dropped %s manifest entr(y/ies) with non-numeric first_seen", len(loaded) - len(manifest))

        # ── Add all known npvt/npvtsub records from state DB ────────
        source_ids = [s.id for s in self.config.sources]
        history_records = self.repo.get_records_for_build(["npvt", "npvtsub"], source_ids)

        added = 0
        for rec in history_records:
            data = rec.get("data")
            if not isinstance(data, dict):
                continue
            line = data.get("line")
            if not isinstance(line, str):
                continue
            uri = line.strip()
            if not uri or "://" not in uri:
                continue
            key = strip_proxy_remark(uri)
            if key not in manifest:
                manifest[key] = now
                added += 1

        logger.info(
            f"[DevExport] Manifest: {len(manifest) - added} existing + {added} added " f"= {len(manifest)} total"
        )

        if not manifest:
            logger.warning("[DevExport] No proxy URIs found — outputs_dev/ not updated.")
            return

        # ── Save manifest ─────────────────────────────────────────────
        atomic_write(manifest_path, json.dumps(manifest).encode("utf-8"))

        # ── Sort URIs deterministically (newest first, then alpha) ────
        sorted_uris = sorted(manifest.keys(), key=lambda u: (-manifest[u], u))
        ts_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # ── Add clean protocol-N remarks for output ────────────────────
        remark_counter: dict = {}
        remarked_uris = [add_clean_remark(u, remark_counter) for u in sorted_uris]

        # ── proxies.txt ───────────────────────────────────────────────
        txt_path = dev_dir / "proxies.txt"
        header = (
            f"# huntx proxy list \u2014 {ts_str}\n"
            f"# All-time cumulative history \u2014 {len(remarked_uris)} unique URIs\n"
            f"# One proxy URI per line\n\n"
        )
        atomic_write(txt_path, header + "\n".join(remarked_uris) + "\n", mode="w")
        logger.info(
            f"[DevExport] Written {txt_path.name} "
            f"({len(sorted_uris)} URIs, {txt_path.stat().st_size / 1024:.1f} KB)"
        )

        # ── proxies_b64sub.txt ────────────────────────────────────────
        b64_path = dev_dir / "proxies_b64sub.txt"
        plain = "\n".join(remarked_uris)
        b64_payload = base64.b64encode(plain.encode("utf-8")).decode("ascii")
        atomic_write(b64_path, b64_payload + "\n", mode="w")
        logger.info(f"[DevExport] Written {b64_path.name} " f"({b64_path.stat().st_size / 1024:.1f} KB)")

        # ── proxies.json ─────────────────────────────────────────────
        json_path = dev_dir / "proxies.json"
        wrapped = {
            "_generated": ts_str,
            "_scope": "all_time_cumulative",
            "_count": len(sorted_uris),
            "proxies": [
                {"uri": remarked, "first_seen": manifest[raw]} for raw, remarked in zip(sorted_uris, remarked_uris)
            ],
        }
        atomic_write(json_path, json.dumps(wrapped, indent=2, ensure_ascii=False), mode="w")
        logger.info(f"[DevExport] Written {json_path.name} " f"({json_path.stat().st_size / 1024:.1f} KB)")

        logger.info(f"[DevExport] Exported 3 file(s) to {dev_dir}")

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _get_build_window_start(self, run_started_at: datetime.datetime | None = None) -> str:
        """Resolve one UTC ingestion cutoff per run; never infer time from IDs."""
        raw = os.environ.get("HUNTX_OUTPUT_RETENTION_DAYS", str(self.OUTPUT_RETENTION_DAYS))
        try:
            days = int(raw)
            if days <= 0:
                raise ValueError
        except ValueError as exc:
            raise ValueError("HUNTX_OUTPUT_RETENTION_DAYS must be a positive integer") from exc
        start = run_started_at or datetime.datetime.now(datetime.timezone.utc)
        if start.tzinfo is None:
            raise ValueError("Run start must be timezone-aware")
        cutoff = start.astimezone(datetime.timezone.utc) - datetime.timedelta(days=days)
        return cutoff.strftime("%Y-%m-%d %H:%M:%S")

    def _record_http_source_failure(
        self, source_id: str, error_type: str, *, infrastructure: bool = False
    ) -> None:
        """Keep local worker failures out of upstream feed reliability history.

        Infrastructure failures do not prove the feed is down; they must never
        inflate the feed's failure streak or contaminate its Wilson estimate.
        """
        summaries = getattr(self, "_http_source_reports", None)
        previous: dict[str, Any] = {}
        try:
            previous = self.repo.get_source_state(source_id) or {}
            now = int(time.time())
            if infrastructure:
                previous["last_infrastructure_failure_at"] = now
                previous["last_infrastructure_error_type"] = error_type
            else:
                previous["total_failures"] = min(
                    1_000_000, int(previous.get("total_failures", 0)) + 1
                )
                previous["consecutive_failures"] = min(
                    1_000_000, int(previous.get("consecutive_failures", 0)) + 1
                )
                previous["last_failed_at"] = now
                previous["last_error_type"] = error_type
                previous["retrieval_history"] = append_retrieval_observation(
                    previous, success=False, now=now
                )
            self.repo.update_source_state(
                source_id, previous, source_type="http_subscription"
            )
        except Exception:
            logger.exception(
                "[HTTP Feed] could not persist failure history for source %s", source_id
            )
        if isinstance(summaries, dict):
            summaries[source_id] = {
                "status": "infrastructure_error" if infrastructure else "failed",
                "error_type": error_type,
                "validation": "not_accepted",
                "consecutive_failures": previous.get("consecutive_failures", 0),
                "last_success_at": previous.get("last_success_at"),
                "availability": summarize_source_reliability(previous),
            }

    async def _ingest_one_source_async(self, src_conf) -> bool:
        """Ingest a single source asynchronously."""
        from ..connectors.telegram.connector import TelegramConnector
        from ..connectors.telegram_user.connector import TelegramUserConnector

        try:
            deadline = getattr(self, "_deadline", None)
            if src_conf.type == "telegram" and src_conf.telegram:
                if not src_conf.telegram.token:
                    logger.warning(f"[Worker] Skipping {src_conf.id}: Missing Telegram bot token.")
                    return False

                logger.info(f"[Worker] Ingesting source {src_conf.id} (Bot API)")
                bot_conn = TelegramConnector(
                    token=src_conf.telegram.token,
                    chat_id=src_conf.telegram.chat_id,
                    state=self.repo.get_source_state(src_conf.id),
                    fetch_windows=self.fetch_windows,
                    inbox=self.repo,
                )
                bot_conn.deadline = deadline
                await maybe_await(
                    self.ingest_pipeline.run(src_conf.id, bot_conn, source_type=src_conf.type, deadline=deadline)
                )
                return True
            elif src_conf.type == "telegram_user" and src_conf.telegram_user:
                if not src_conf.telegram_user.api_id or not src_conf.telegram_user.api_hash:
                    logger.warning(f"[Worker] Skipping {src_conf.id}: Missing API ID or Hash.")
                    return False

                logger.info(f"[Worker] Ingesting source {src_conf.id} (MTProto)")
                user_conn = TelegramUserConnector(
                    api_id=src_conf.telegram_user.api_id,
                    api_hash=src_conf.telegram_user.api_hash,
                    session=src_conf.telegram_user.session,
                    peer=src_conf.telegram_user.peer,
                    state=self.repo.get_source_state(src_conf.id),
                    fetch_windows=self.fetch_windows,
                )
                user_conn.deadline = deadline
                async with user_conn:
                    # Dedup: resolve canonical channel ID and skip if already seen
                    channel_id = await maybe_await(user_conn.resolve_channel_id_async())
                    if channel_id is not None:
                        with self._seen_lock:
                            if channel_id in self._seen_channels:
                                logger.warning(
                                    f"[Worker] Skipping {src_conf.id} — channel {channel_id} "
                                    f"already ingested by another source"
                                )
                                return True  # not an error, just a dup
                            self._seen_channels.add(channel_id)
                    await maybe_await(
                        self.ingest_pipeline.run(src_conf.id, user_conn, source_type=src_conf.type, deadline=deadline)
                    )
                return True
            elif src_conf.type == "http_subscription" and src_conf.http_subscription:
                from ..connectors.http_subscription.connector import HttpSubscriptionConnector

                feed = src_conf.http_subscription
                connector = HttpSubscriptionConnector(
                    url=feed.url,
                    mode=feed.mode,
                    timeout_seconds=feed.timeout_seconds,
                    raw_store=self.raw_store,
                )
                connector.deadline = deadline
                await self.ingest_pipeline.run(
                    src_conf.id, connector, source_type=src_conf.type, deadline=deadline
                )
                feed_state = connector.get_state()
                report = feed_state.get("report", {})
                summaries = getattr(self, "_http_source_reports", None)
                if isinstance(summaries, dict):
                    summaries[str(src_conf.id)] = {
                        "status": "parsed" if feed.mode == "auto" else "audited",
                        "checked_at": feed_state.get("checked_at"),
                        "last_changed_at": feed_state.get("last_changed_at"),
                        "revalidated": bool(feed_state.get("revalidated", False)),
                        "nodes": int(report.get("nodes", 0)),
                        "profiles": int(report.get("profiles", 0)),
                        "policy_bound": int(report.get("policy_bound_endpoints", 0)),
                        "skipped_incompatible": int(report.get("skipped_incompatible", 0)),
                        "validation": "syntax_only",
                        "availability": summarize_source_reliability(feed_state),
                    }
                return True
            elif src_conf.type == "v2ray_collector":
                logger.info(f"[Worker] Ingesting source {src_conf.id} (Go v2ray_collector)")
                from ..connectors.v2ray_collector.connector import V2RayCollectorConnector

                # Determine absolute path to the v2ray_collector connector directory
                connector_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "connectors", "v2ray_collector"
                )
                collector_conn = V2RayCollectorConnector(base_dir=connector_dir)
                collector_conn.deadline = deadline
                await maybe_await(
                    self.ingest_pipeline.run(src_conf.id, collector_conn, source_type=src_conf.type, deadline=deadline)
                )
                return True
            else:
                logger.warning(f"[Worker] Skipping {src_conf.id}: unsupported type.")
                return False
        except Exception as e:
            if src_conf.type == "http_subscription":
                from ..connectors.http_subscription.connector import GoFeedWorkerUnavailable

                infrastructure = isinstance(e, GoFeedWorkerUnavailable)
                self._record_http_source_failure(
                    str(src_conf.id), type(e).__name__, infrastructure=infrastructure
                )
                logger.error(
                    "[HTTP Feed] %s source=%s error_type=%s",
                    "worker unavailable" if infrastructure else "retrieval failed",
                    src_conf.id, type(e).__name__,
                )
                return False
            logger.exception(f"[Worker] Ingest failed for {src_conf.id}: {e}")
            return False

    async def _worker_async(self, source_queue: asyncio.Queue, results: dict, lock: asyncio.Lock):
        """Async queue worker."""
        while not source_queue.empty():
            try:
                src_conf = source_queue.get_nowait()
            except asyncio.QueueEmpty:
                return  # pool exhausted

            success = await self._ingest_one_source_async(src_conf)
            async with lock:
                if success:
                    results["ok"] += 1
                elif getattr(src_conf, "required", True):
                    results["err"] += 1
                else:
                    results["optional_err"] = results.get("optional_err", 0) + 1
            source_queue.task_done()

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ):
        # run_sync handles both cases: a fresh loop via asyncio.run when none
        # is running, or a dedicated worker thread when called from inside a
        # running loop. It avoids the deprecated get_event_loop() (which
        # raises on Python 3.12+ when no loop was ever set) and does not leak
        # an unclosed loop from new_event_loop().
        return run_sync(
            self._run_async(
                timeout,
                no_publish,
                allow_partial_export=allow_partial_export,
            )
        )

    async def _run_async(
        self,
        timeout: float | None = None,
        no_publish: bool = False,
        allow_partial_export: bool = False,
    ):
        """Run through the single deadline-aware orchestration contract."""
        # Imported lazily to avoid an import cycle: HardenedOrchestrator is a
        # compatibility subclass of this class, while its implementation is
        # also the authoritative execution contract for legacy callers.
        from .hardened_orchestrator import HardenedOrchestrator

        return await HardenedOrchestrator._run_hardened(
            self,  # type: ignore[arg-type]
            timeout,
            no_publish,
            allow_partial_export,
        )

    async def _run_async_legacy(self, timeout: float | None = None, no_publish: bool = False):
        start_time = time.time()
        self._deadline = start_time + timeout if timeout else None
        run_id = int(start_time)
        total_sources = len(self.config.sources)
        total_routes = len(self.config.routes)
        effective_workers = min(self.max_workers, total_sources)
        min_ingested_at = self._get_build_window_start()

        # Initialize results early so they exist even if we timeout early
        results = {"ok": 0, "err": 0}
        ingest_duration: float = 0.0
        transform_duration: float = 0.0
        build_duration: float = 0.0
        total_artifacts = 0
        publish_failures = 0
        publish_attempts = 0
        failed_routes = set()
        all_build_results = []
        cleanup_duration: float = 0.0

        def _raise_if_timed_out(stage: str):
            if timeout is None:
                return
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"[Orchestrator] Run timed out after {elapsed:.1f}s during {stage} " f"(timeout={timeout:.1f}s)"
                )

        logger.info(
            f"[Orchestrator] ╔══════════════════════════════════════════╗\n"
            f"[Orchestrator] ║  Run {run_id}                              ║\n"
            f"[Orchestrator] ╚══════════════════════════════════════════╝\n"
            f"[Orchestrator] sources={total_sources}  routes={total_routes}  "
            f"workers={effective_workers}  fetch_windows={self.fetch_windows}  "
            f"ingested_at>={min_ingested_at}  timeout={timeout}"
        )

        # ── Phase 1: Ingestion (async queue-based) ───────────────────
        try:
            ingest_start = time.time()
            source_queue: asyncio.Queue[Any] = asyncio.Queue()
            for src in self.config.sources:
                await source_queue.put(src)

            lock = asyncio.Lock()

            logger.info(
                f"[Orchestrator] ═══ Phase 1: Ingestion ═══  " f"sources={total_sources}  workers={effective_workers}"
            )

            tasks = []
            for _ in range(effective_workers):
                t = asyncio.create_task(self._worker_async(source_queue, results, lock))
                tasks.append(t)

            if timeout is None:
                await asyncio.gather(*tasks)
            else:
                remaining = timeout - (time.time() - start_time)
                if remaining > 0:
                    await asyncio.wait_for(asyncio.gather(*tasks), timeout=remaining)
                else:
                    raise TimeoutError("Timeout exceeded before starting ingestion workers.")

            ingest_duration = time.time() - ingest_start
            logger.info(
                f"[Orchestrator] Phase 1 done: {results['ok']} ok / {results['err']} failed  "
                f"duration={ingest_duration:.2f}s"
            )
            _raise_if_timed_out("phase 1 ingestion")
        except (TimeoutError, asyncio.TimeoutError) as e:
            logger.warning(f"[Orchestrator] Phase 1 interrupted by timeout: {e}")

        # ── Phase 2: Transform ───────────────────────────────────────
        try:
            transform_start = time.time()
            logger.info("[Orchestrator] ═══ Phase 2: Transformation ═══")
            # If we are already timed out, this check ensures we don't start Phase 2 needlessly
            _raise_if_timed_out("phase 2 start")

            try:
                self.transform_pipeline.process_pending()
            except Exception as e:
                logger.exception(f"[Orchestrator] Transform failed: {e}")

            transform_duration = time.time() - transform_start
            logger.info(f"[Orchestrator] Phase 2 done: duration={transform_duration:.2f}s")
            _raise_if_timed_out("phase 2 completion")
        except TimeoutError as e:
            logger.warning(f"[Orchestrator] Phase 2 interrupted/skipped by timeout: {e}")

        # ── Phase 3: Build & Publish ─────────────────────────────────
        # We proceed to Phase 3 even if timed out, to generate artifacts from whatever data we have.
        build_start = time.time()
        logger.info(f"[Orchestrator] ═══ Phase 3: Build & Publish ═══  routes={total_routes}")

        try:
            # Create executor once for all routes to reduce overhead
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pub_executor:
                # Optimization: Collect all futures across all routes first.
                # This allows Route B to start building while Route A is still publishing (I/O wait).
                future_to_meta = {}

                for route in self.config.routes:
                    try:
                        # Removed _raise_if_timed_out check here to ensure we try to build

                        route_dict = {
                            "name": route.name,
                            "formats": route.formats,
                            "from_sources": route.from_sources,
                            "min_ingested_at": min_ingested_at,
                        }
                        build_results = self.build_pipeline.run(route_dict)
                        if not build_results:
                            logger.info(f"[Orchestrator] Route '{route.name}': no artifacts produced.")
                            continue

                        total_artifacts += len(build_results)
                        all_build_results.extend(build_results)

                        dests = [
                            {
                                "chat_id": d.chat_id,
                                "mode": d.mode,
                                "caption_template": d.caption_template,
                                "token": d.token,
                            }
                            for d in route.destinations
                        ]

                        # Submit tasks to the shared executor
                        if not no_publish:
                            for res in build_results:
                                # Removed _raise_if_timed_out check here
                                fut = pub_executor.submit(self.publish_pipeline.run, res, dests)
                                future_to_meta[fut] = {
                                    "route": route.name,
                                    "artifact": res.get("unique_id", "unknown") if isinstance(res, dict) else str(res),
                                }
                        else:
                            logger.info(f"[Orchestrator] Skipping publish for route '{route.name}' (--no-publish)")

                    except Exception as e:
                        logger.exception(f"[Orchestrator] Build/Publish failed for '{route.name}': {e}")
                        failed_routes.add(route.name)

                # Now wait for all publish tasks to complete
                publish_wait_timeout = None
                if timeout is not None:
                    publish_wait_timeout = max(0.0, timeout - (time.time() - start_time))

                try:
                    for future in concurrent.futures.as_completed(
                        future_to_meta,
                        timeout=publish_wait_timeout,
                    ):
                        meta = future_to_meta[future]
                        publish_attempts += 1
                        try:
                            future.result()
                        except Exception as e:
                            publish_failures += 1
                            failed_routes.add(meta["route"])
                            logger.error(
                                f"[Orchestrator] Publish failed for route='{meta['route']}' "
                                f"artifact='{meta['artifact']}': {e}"
                            )
                        # Removed _raise_if_timed_out check here
                except (concurrent.futures.TimeoutError, TimeoutError) as e:
                    logger.warning(f"[Orchestrator] Publishing timed out, some artifacts may not be delivered: {e}")
                    # We continue to export logic
        except Exception as e:
            logger.exception(f"[Orchestrator] Phase 3 fatal error: {e}")

        build_err = len(failed_routes)
        build_ok = total_routes - build_err

        build_duration = time.time() - build_start
        logger.info(
            f"[Orchestrator] Phase 3 done: routes={build_ok} ok / {build_err} err  "
            f"artifacts={total_artifacts}  publish_attempts={publish_attempts}  "
            f"publish_failures={publish_failures}  "
            f"duration={build_duration:.2f}s"
        )

        # ── Phase 3b: Export outputs to repo ──────────────────────────
        try:
            self._export_outputs(all_build_results)
        except Exception as e:
            logger.error(f"[Orchestrator] Output export failed: {e}")

        try:
            self._export_dev_outputs(all_build_results)
        except Exception as e:
            logger.error(f"[Orchestrator] Dev export failed: {e}")

        # ── Phase 4: Cleanup raw cache for processed files ───────────
        try:
            cleanup_start = time.time()
            logger.info("[Orchestrator] ═══ Phase 4: Cleanup ═══")
            self.raw_store.prune_processed(self.repo)
            self.raw_store.prune_orphans(self.repo)
            self.artifact_store.prune_archive()

            # Auto-prune database records and disk raw store files older than N days (default: 30)
            try:
                prune_days_str = os.environ.get("HUNTX_PRUNE_DAYS", "30")
                prune_days = int(prune_days_str)
            except ValueError:
                prune_days = 30

            logger.info(f"[Orchestrator] Auto-pruning database and raw store older than {prune_days} days...")
            prune_res = self.repo.prune_old_data(prune_days)
            if prune_res["raw_hashes"]:
                raw_pruned = self.raw_store.prune_by_hashes(prune_res["raw_hashes"])
                logger.info(f"[Orchestrator] Pruned {raw_pruned} raw store files from disk during auto-prune.")
            cleanup_duration = time.time() - cleanup_start
        except Exception as e:
            logger.error(f"[Orchestrator] Cleanup failed: {e}")

        duration = time.time() - start_time

        logger.info(
            f"[Orchestrator] ╔══════════════════════════════════════════╗\n"
            f"[Orchestrator] ║  Run {run_id} COMPLETE                     ║\n"
            f"[Orchestrator] ╚══════════════════════════════════════════╝\n"
            f"[Orchestrator] Total duration: {duration:.2f}s\n"
            f"[Orchestrator]   Phase 1 Ingest:    {ingest_duration:.1f}s  ({results['ok']} ok, {results['err']} err)\n"
            f"[Orchestrator]   Phase 2 Transform: {transform_duration:.1f}s\n"
            f"[Orchestrator]   Phase 3 Build/Pub: {build_duration:.1f}s  "
            f"({total_artifacts} artifacts, {publish_failures} publish failures)\n"
            f"[Orchestrator]   Phase 4 Cleanup:   {cleanup_duration:.1f}s"
        )

        if build_err > 0:
            # Resilience: Log error but do not crash the process.
            # This ensures partial success is preserved and CI doesn't mark the whole job as failed.
            logger.error(f"[Orchestrator] Run completed with issues: {build_err} routes had failures.")

        return {
            "total_artifacts": total_artifacts,
            "publish_attempts": publish_attempts,
            "publish_failures": publish_failures,
            "ingest_ok": results["ok"],
            "ingest_err": results["err"],
            "failed_routes": len(failed_routes),
        }
