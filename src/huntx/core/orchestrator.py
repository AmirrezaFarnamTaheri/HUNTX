import asyncio
import base64
import datetime
import json
import logging
import time
import queue
import threading
from pathlib import Path
from ..store.paths import STATE_DB_PATH
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

logger = logging.getLogger(__name__)

# Default number of parallel ingestion workers
DEFAULT_MAX_WORKERS = 2


class Orchestrator:
    def __init__(self, config: AppConfig, max_workers: int = DEFAULT_MAX_WORKERS, fetch_windows: dict = None):
        logger.info("[Orchestrator] Initializing...")
        self.config = config
        self.max_workers = max_workers
        self.fetch_windows = fetch_windows or {
            "msg_fresh_hours": 2,
            "file_fresh_hours": 48,
            "msg_subsequent_hours": 0,
            "file_subsequent_hours": 0,
        }

        self.raw_store = RawStore()
        self.artifact_store = ArtifactStore()

        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)
        logger.debug(f"[Orchestrator] State DB at {STATE_DB_PATH}")

        self.registry = FormatRegistry.get_instance()
        register_all_formats(self.registry, self.raw_store)

        source_configs = {s.id: s for s in self.config.sources}

        self.ingest_pipeline = IngestionPipeline(self.raw_store, self.repo)
        self.transform_pipeline = TransformPipeline(self.raw_store, self.repo, self.registry, source_configs)
        self.build_pipeline = BuildPipeline(self.repo, self.artifact_store, self.registry)
        self.publish_pipeline = PublishPipeline(self.repo)
        self._seen_channels: set = set()   # canonical channel IDs for dedup
        self._seen_lock = threading.Lock()
        logger.info(
            f"[Orchestrator] Ready — {len(self.config.sources)} sources, "
            f"{len(self.config.routes)} routes, {self.max_workers} workers."
        )

    # ------------------------------------------------------------------
    # Output export
    # ------------------------------------------------------------------

    def _iter_expected_output_keys(self):
        """Yield (route_name, format_id) keys expected by current config."""
        for route in self.config.routes:
            for fmt in route.formats:
                yield route.name, fmt
                if fmt in ("npvt", "npvtsub"):
                    yield route.name, f"{fmt}.decoded.json"
                    yield route.name, f"{fmt}.b64sub"

    def _load_latest_archive_artifact(self, route: str, fmt: str):
        """
        Load latest archived bytes for route+format.
        Returns None if no matching archive artifact exists.
        """
        archive_dir = self.artifact_store.archive_dir
        if not archive_dir.exists():
            return None

        prefix = f"{route}_"
        suffix = f".{fmt}"
        latest_path = None
        latest_ts = -1

        for item in archive_dir.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if not (name.startswith(prefix) and name.endswith(suffix)):
                continue

            middle = name[len(prefix): -len(suffix)]
            if middle.isdigit():
                ts = int(middle)
            else:
                try:
                    ts = int(item.stat().st_mtime)
                except OSError:
                    continue

            if ts > latest_ts:
                latest_ts = ts
                latest_path = item

        if not latest_path:
            return None

        try:
            return latest_path.read_bytes()
        except OSError as e:
            logger.warning(f"[Export] Could not read archived artifact {latest_path.name}: {e}")
            return None

    def _export_outputs(self, all_build_results: list):
        """Write all build artifacts to outputs/ in the repo root.
        These are committed back to the repo by CI."""
        out_dir = Path.cwd() / "outputs"
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

        # Backfill missing promised outputs from archive snapshots.
        for route, fmt in self._iter_expected_output_keys():
            filename = self._output_filename(route, fmt)
            if filename in output_payloads:
                continue
            if (out_dir / filename).exists():
                continue
            archived_data = self._load_latest_archive_artifact(route, fmt)
            if archived_data is None:
                continue
            output_payloads[filename] = archived_data
            logger.info(f"[Export] Restored {filename} from archive")

        expected_filenames = {
            self._output_filename(route, fmt) for route, fmt in self._iter_expected_output_keys()
        }

        # Remove stale route files that are no longer part of expected naming.
        routes_in_play = {r.name for r in self.config.routes}
        stale_removed = 0
        for existing in out_dir.iterdir():
            if not existing.is_file():
                continue
            # Skip non-pipeline files (README, scripts, etc.)
            name = existing.name
            if not any(name.startswith(rt) for rt in routes_in_play):
                continue
            if name in output_payloads:
                continue
            # Keep expected files even when this run did not rebuild them.
            if name in expected_filenames:
                continue
            # This is a route-owned file that is NOT in the new set → stale
            try:
                existing.unlink()
                stale_removed += 1
                logger.info(f"[Export] Removed stale output: {name}")
            except OSError as e:
                logger.warning(f"[Export] Could not remove stale file {name}: {e}")
        if stale_removed:
            logger.info(f"[Export] Cleaned {stale_removed} stale file(s) from {out_dir}")

        # ── Write new outputs ─────────────────────────────────────────
        files_written = 0
        total_bytes = 0

        for filename, data in output_payloads.items():
            path = out_dir / filename
            try:
                if isinstance(data, bytes):
                    path.write_bytes(data)
                else:
                    path.write_text(str(data), encoding="utf-8")
                size = path.stat().st_size
                total_bytes += size
                files_written += 1
                logger.info(f"[Export] Written {filename} ({size / 1024:.1f} KB)")
            except Exception as e:
                logger.error(f"[Export] Failed to write {filename}: {e}")

        if files_written == 0:
            logger.warning("[Export] No artifacts produced — outputs/ not updated.")
        else:
            logger.info(
                f"[Export] Exported {files_written} file(s) to {out_dir} "
                f"({total_bytes / 1024:.1f} KB total)"
            )

    @staticmethod
    def _output_filename(route: str, fmt: str) -> str:
        """Determine the output filename for a route+format pair."""
        if fmt.endswith(".decoded.json"):
            return f"{route}_{fmt.replace('.decoded.json', '')}_decoded.json"
        elif fmt.endswith(".b64sub"):
            return f"{route}_{fmt.replace('.b64sub', '')}_b64sub.txt"
        else:
            return f"{route}.{fmt}"

    # ------------------------------------------------------------------
    # Dev output export
    # ------------------------------------------------------------------

    _DEV_RETENTION_SECONDS = 48 * 3600  # 48-hour rolling window

    def _export_dev_outputs(self, all_build_results: list):
        """Accumulate proxy URIs into outputs_dev/ with a 48-hour rolling window.

        Writes three files from the accumulated state:
          - proxies.txt      — one URI per line
          - proxies.json     — structured JSON with metadata
          - proxies_b64sub.txt — base64-encoded subscription
        A hidden _manifest.json tracks {uri: last_seen_timestamp} for dedup
        and pruning across runs.
        """
        dev_dir = Path.cwd() / "outputs_dev"
        dev_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = dev_dir / "_manifest.json"
        now = time.time()

        # ── Load existing manifest ────────────────────────────────────
        manifest: dict = {}  # {uri_string: last_seen_epoch}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[DevExport] Could not read manifest, starting fresh: {e}")

        # ── Seed manifest from existing outputs/ artifacts ──────────
        # Ensures dedup even after a reset or when manifest is empty
        out_dir = Path.cwd() / "outputs"
        seeded = 0
        for npvt_file in out_dir.glob("*.npvt"):
            try:
                text = npvt_file.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    uri = line.strip()
                    if uri and "://" in uri:
                        key = strip_proxy_remark(uri)
                        if key not in manifest:
                            manifest[key] = now
                            seeded += 1
            except OSError as e:
                logger.warning(f"[DevExport] Could not read {npvt_file.name} for seeding: {e}")
        if seeded:
            logger.info(f"[DevExport] Seeded {seeded} URIs from existing outputs/")

        # ── Extract new URIs from this run (strip remarks for dedup) ──
        new_uris: list = []
        for res in all_build_results:
            if not isinstance(res, dict):
                continue
            fmt = res.get("format", "")
            if fmt not in ("npvt", "npvtsub"):
                continue
            data = res.get("data")
            if not data:
                continue
            text = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
            for line in text.splitlines():
                uri = line.strip()
                if uri and "://" in uri:
                    new_uris.append(strip_proxy_remark(uri))

        added = 0
        for uri in new_uris:
            if uri not in manifest:
                added += 1
            manifest[uri] = now

        # ── Prune entries older than 48 hours ─────────────────────────
        cutoff = now - self._DEV_RETENTION_SECONDS
        before = len(manifest)
        manifest = {uri: ts for uri, ts in manifest.items() if ts >= cutoff}
        pruned = before - len(manifest)

        logger.info(
            f"[DevExport] Manifest: {before} existing + {added} new - {pruned} expired "
            f"= {len(manifest)} total"
        )

        if not manifest:
            logger.warning("[DevExport] No proxy URIs in rolling window — outputs_dev/ not updated.")
            return

        # ── Save manifest ─────────────────────────────────────────────
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

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
            f"# Rolling 48h window \u2014 {len(remarked_uris)} unique URIs\n"
            f"# One proxy URI per line\n\n"
        )
        txt_path.write_text(header + "\n".join(remarked_uris) + "\n", encoding="utf-8")
        logger.info(
            f"[DevExport] Written {txt_path.name} "
            f"({len(sorted_uris)} URIs, {txt_path.stat().st_size / 1024:.1f} KB)"
        )

        # ── proxies_b64sub.txt ────────────────────────────────────────
        b64_path = dev_dir / "proxies_b64sub.txt"
        plain = "\n".join(remarked_uris)
        b64_payload = base64.b64encode(plain.encode("utf-8")).decode("ascii")
        b64_path.write_text(b64_payload + "\n", encoding="utf-8")
        logger.info(
            f"[DevExport] Written {b64_path.name} "
            f"({b64_path.stat().st_size / 1024:.1f} KB)"
        )

        # ── proxies.json ─────────────────────────────────────────────
        json_path = dev_dir / "proxies.json"
        wrapped = {
            "_generated": ts_str,
            "_window_hours": 48,
            "_count": len(sorted_uris),
            "proxies": [
                {"uri": remarked, "last_seen": manifest[raw]}
                for raw, remarked in zip(sorted_uris, remarked_uris)
            ],
        }
        json_path.write_text(
            json.dumps(wrapped, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            f"[DevExport] Written {json_path.name} "
            f"({json_path.stat().st_size / 1024:.1f} KB)"
        )

        logger.info(f"[DevExport] Exported 3 file(s) to {dev_dir}")

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _ingest_one_source(self, src_conf) -> bool:
        """Ingest a single source. Designed for thread-pool execution."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        from ..connectors.telegram.connector import TelegramConnector
        from ..connectors.telegram_user.connector import TelegramUserConnector

        try:
            if src_conf.type == "telegram" and src_conf.telegram:
                logger.info(f"[Worker] Ingesting source {src_conf.id} (Bot API)")
                bot_conn = TelegramConnector(
                    token=src_conf.telegram.token,
                    chat_id=src_conf.telegram.chat_id,
                    state=self.repo.get_source_state(src_conf.id),
                    fetch_windows=self.fetch_windows,
                )
                self.ingest_pipeline.run(src_conf.id, bot_conn, source_type=src_conf.type)
                return True
            elif src_conf.type == "telegram_user" and src_conf.telegram_user:
                logger.info(f"[Worker] Ingesting source {src_conf.id} (MTProto)")
                user_conn = TelegramUserConnector(
                    api_id=src_conf.telegram_user.api_id,
                    api_hash=src_conf.telegram_user.api_hash,
                    session=src_conf.telegram_user.session,
                    peer=src_conf.telegram_user.peer,
                    state=self.repo.get_source_state(src_conf.id),
                    fetch_windows=self.fetch_windows,
                )
                # Dedup: resolve canonical channel ID and skip if already seen
                channel_id = user_conn.resolve_channel_id()
                if channel_id is not None:
                    with self._seen_lock:
                        if channel_id in self._seen_channels:
                            logger.warning(
                                f"[Worker] Skipping {src_conf.id} — channel {channel_id} "
                                f"already ingested by another source"
                            )
                            user_conn.cleanup()
                            return True  # not an error, just a dup
                        self._seen_channels.add(channel_id)
                try:
                    self.ingest_pipeline.run(src_conf.id, user_conn, source_type=src_conf.type)
                    return True
                finally:
                    # Ensure cleanup happens even if ingest fails
                    user_conn.cleanup()
            else:
                logger.warning(f"[Worker] Skipping {src_conf.id}: unsupported type.")
                return False
        except Exception as e:
            logger.exception(f"[Worker] Ingest failed for {src_conf.id}: {e}")
            return False

    def _worker(self, source_queue: queue.Queue, results: dict, lock: threading.Lock):
        """
        Pool worker: pull sources from the shared queue until it is empty.
        Each source is fully processed before the next one is taken, and
        no two workers can take the same source (guaranteed by queue).
        """
        while True:
            try:
                src_conf = source_queue.get_nowait()
            except queue.Empty:
                return  # pool exhausted

            success = self._ingest_one_source(src_conf)
            with lock:
                if success:
                    results["ok"] += 1
                else:
                    results["err"] += 1
            source_queue.task_done()

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self):
        start_time = time.time()
        run_id = int(start_time)
        total_sources = len(self.config.sources)
        total_routes = len(self.config.routes)
        effective_workers = min(self.max_workers, total_sources)

        logger.info(
            f"[Orchestrator] ╔══════════════════════════════════════════╗\n"
            f"[Orchestrator] ║  Run {run_id}                              ║\n"
            f"[Orchestrator] ╚══════════════════════════════════════════╝\n"
            f"[Orchestrator] sources={total_sources}  routes={total_routes}  "
            f"workers={effective_workers}  fetch_windows={self.fetch_windows}"
        )

        # ── Phase 1: Ingestion (pool-based) ──────────────────────────
        ingest_start = time.time()
        source_queue: queue.Queue = queue.Queue()
        for src in self.config.sources:
            source_queue.put(src)

        results = {"ok": 0, "err": 0}
        lock = threading.Lock()

        logger.info(
            f"[Orchestrator] ═══ Phase 1: Ingestion ═══  "
            f"sources={total_sources}  workers={effective_workers}"
        )

        threads = []
        for _ in range(effective_workers):
            t = threading.Thread(target=self._worker, args=(source_queue, results, lock), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        ingest_duration = time.time() - ingest_start
        logger.info(
            f"[Orchestrator] Phase 1 done: {results['ok']} ok / {results['err']} failed  "
            f"duration={ingest_duration:.2f}s"
        )

        # ── Phase 2: Transform ───────────────────────────────────────
        transform_start = time.time()
        logger.info("[Orchestrator] ═══ Phase 2: Transformation ═══")
        try:
            self.transform_pipeline.process_pending()
        except Exception as e:
            logger.exception(f"[Orchestrator] Transform failed: {e}")
        transform_duration = time.time() - transform_start
        logger.info(f"[Orchestrator] Phase 2 done: duration={transform_duration:.2f}s")

        # ── Phase 3: Build & Publish ─────────────────────────────────
        build_start = time.time()
        logger.info(
            f"[Orchestrator] ═══ Phase 3: Build & Publish ═══  routes={total_routes}"
        )

        build_ok = 0
        build_err = 0
        total_artifacts = 0
        publish_attempts = 0
        all_build_results = []

        for route in self.config.routes:
            try:
                route_dict = {
                    "name": route.name,
                    "formats": route.formats,
                    "from_sources": route.from_sources,
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

                for res in build_results:
                    self.publish_pipeline.run(res, dests)
                    publish_attempts += 1
                build_ok += 1
            except Exception as e:
                logger.exception(f"[Orchestrator] Build/Publish failed for '{route.name}': {e}")
                build_err += 1

        build_duration = time.time() - build_start
        logger.info(
            f"[Orchestrator] Phase 3 done: routes={build_ok} ok / {build_err} err  "
            f"artifacts={total_artifacts}  publish_attempts={publish_attempts}  "
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
        cleanup_start = time.time()
        logger.info("[Orchestrator] ═══ Phase 4: Cleanup ═══")
        self.raw_store.prune_processed(self.repo)
        self.artifact_store.prune_archive()
        cleanup_duration = time.time() - cleanup_start

        duration = time.time() - start_time

        logger.info(
            f"[Orchestrator] ╔══════════════════════════════════════════╗\n"
            f"[Orchestrator] ║  Run {run_id} COMPLETE                     ║\n"
            f"[Orchestrator] ╚══════════════════════════════════════════╝\n"
            f"[Orchestrator] Total duration: {duration:.2f}s\n"
            f"[Orchestrator]   Phase 1 Ingest:    {ingest_duration:.1f}s  ({results['ok']} ok, {results['err']} err)\n"
            f"[Orchestrator]   Phase 2 Transform: {transform_duration:.1f}s\n"
            f"[Orchestrator]   Phase 3 Build/Pub: {build_duration:.1f}s  ({total_artifacts} artifacts)\n"
            f"[Orchestrator]   Phase 4 Cleanup:   {cleanup_duration:.1f}s"
        )
