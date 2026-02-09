import asyncio
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
        logger.info(
            f"[Orchestrator] Ready — {len(self.config.sources)} sources, "
            f"{len(self.config.routes)} routes, {self.max_workers} workers."
        )

    # ------------------------------------------------------------------
    # Output export
    # ------------------------------------------------------------------

    def _export_outputs(self, all_build_results: list):
        """Write all build artifacts to outputs/ in the repo root.
        These are committed back to the repo by CI."""
        out_dir = Path.cwd() / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        files_written = 0
        total_bytes = 0

        for res in all_build_results:
            route = res.get("route_name", "unknown")
            fmt = res.get("format", "unknown")
            data = res.get("data")
            if not data:
                continue

            # Determine filename from route + format
            if fmt.endswith(".decoded.json"):
                filename = f"{route}_{fmt.replace('.decoded.json', '')}_decoded.json"
            elif fmt.endswith(".b64sub"):
                filename = f"{route}_{fmt.replace('.b64sub', '')}_b64sub.txt"
            else:
                filename = f"{route}.{fmt}"
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

    # ------------------------------------------------------------------
    # Dev output export
    # ------------------------------------------------------------------

    def _export_dev_outputs(self, all_build_results: list):
        """Write proxies.txt and proxies.json to outputs_dev/ in the repo root.
        These are committed back to the repo by CI for easy access."""
        dev_dir = Path.cwd() / "outputs_dev"
        dev_dir.mkdir(parents=True, exist_ok=True)

        raw_text_data = None
        decoded_json_data = None

        for res in all_build_results:
            fmt = res.get("format", "")
            # Pick the primary npvt text artifact (raw proxy lines)
            if fmt == "npvt" and raw_text_data is None:
                raw_text_data = res.get("data")
            # Pick the decoded JSON artifact
            if fmt == "npvt.decoded.json" and decoded_json_data is None:
                decoded_json_data = res.get("data")

        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        files_written = 0

        # Write proxies.txt
        if raw_text_data:
            txt_path = dev_dir / "proxies.txt"
            header = f"# MergeBot proxy list — auto-generated {ts}\n# One proxy URI per line\n\n"
            if isinstance(raw_text_data, bytes):
                payload = raw_text_data.decode("utf-8", errors="ignore")
            else:
                payload = str(raw_text_data)
            line_count = len([l for l in payload.splitlines() if l.strip()])
            txt_path.write_text(header + payload, encoding="utf-8")
            files_written += 1
            logger.info(f"[DevExport] Written {txt_path} ({line_count} lines, {txt_path.stat().st_size / 1024:.1f} KB)")

        # Write proxies.json
        if decoded_json_data:
            json_path = dev_dir / "proxies.json"
            if isinstance(decoded_json_data, bytes):
                raw_json = decoded_json_data.decode("utf-8", errors="ignore")
            else:
                raw_json = str(decoded_json_data)
            # Re-parse and wrap with metadata
            try:
                parsed = json.loads(raw_json)
                wrapped = {
                    "_generated": ts,
                    "_count": len(parsed) if isinstance(parsed, list) else 1,
                    "proxies": parsed,
                }
                json_path.write_text(json.dumps(wrapped, indent=2, ensure_ascii=False), encoding="utf-8")
            except (json.JSONDecodeError, TypeError):
                # Fallback: write raw
                json_path.write_text(raw_json, encoding="utf-8")
            files_written += 1
            logger.info(f"[DevExport] Written {json_path} ({json_path.stat().st_size / 1024:.1f} KB)")

        if files_written == 0:
            logger.warning("[DevExport] No npvt artifacts found — outputs_dev/ not updated.")
        else:
            logger.info(f"[DevExport] Exported {files_written} file(s) to {dev_dir}")

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
        total_published = 0
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
                    total_published += 1
                build_ok += 1
            except Exception as e:
                logger.exception(f"[Orchestrator] Build/Publish failed for '{route.name}': {e}")
                build_err += 1

        build_duration = time.time() - build_start
        logger.info(
            f"[Orchestrator] Phase 3 done: routes={build_ok} ok / {build_err} err  "
            f"artifacts={total_artifacts}  published={total_published}  "
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
