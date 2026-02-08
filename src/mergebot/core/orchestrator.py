import asyncio
import logging
import time
import queue
import threading
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
    def __init__(self, config: AppConfig, max_workers: int = DEFAULT_MAX_WORKERS):
        logger.info("[Orchestrator] Initializing...")
        self.config = config
        self.max_workers = max_workers

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
                )
                self.ingest_pipeline.run(src_conf.id, user_conn, source_type=src_conf.type)
                return True
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
        effective_workers = min(self.max_workers, total_sources)
        logger.info(f"[Orchestrator] Run {run_id} — {total_sources} sources, {effective_workers} workers")

        # ── Phase 1: Ingestion (pool-based) ──────────────────────────
        ingest_start = time.time()
        source_queue: queue.Queue = queue.Queue()
        for src in self.config.sources:
            source_queue.put(src)

        results = {"ok": 0, "err": 0}
        lock = threading.Lock()

        logger.info(f"[Orchestrator] === Phase 1: Ingestion ({total_sources} sources, {effective_workers} workers) ===")

        threads = []
        for _ in range(effective_workers):
            t = threading.Thread(target=self._worker, args=(source_queue, results, lock), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        ingest_duration = time.time() - ingest_start
        logger.info(
            f"[Orchestrator] Ingestion done in {ingest_duration:.2f}s — "
            f"{results['ok']} ok, {results['err']} failed."
        )

        # ── Phase 2: Transform ───────────────────────────────────────
        transform_start = time.time()
        logger.info("[Orchestrator] === Phase 2: Transformation ===")
        try:
            self.transform_pipeline.process_pending()
        except Exception as e:
            logger.exception(f"[Orchestrator] Transform failed: {e}")
        transform_duration = time.time() - transform_start
        logger.info(f"[Orchestrator] Transform done in {transform_duration:.2f}s.")

        # ── Phase 3: Build & Publish ─────────────────────────────────
        build_start = time.time()
        logger.info(f"[Orchestrator] === Phase 3: Build & Publish ({len(self.config.routes)} routes) ===")

        build_ok = 0
        build_err = 0

        for route in self.config.routes:
            try:
                route_dict = {
                    "name": route.name,
                    "formats": route.formats,
                    "from_sources": route.from_sources,
                }
                build_results = self.build_pipeline.run(route_dict)
                if not build_results:
                    logger.info(f"[Orchestrator] Route '{route.name}': no artifacts.")
                    continue

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
                build_ok += 1
            except Exception as e:
                logger.exception(f"[Orchestrator] Build/Publish failed for '{route.name}': {e}")
                build_err += 1

        build_duration = time.time() - build_start
        duration = time.time() - start_time

        # ── Phase 4: Cleanup raw cache for processed files ───────────
        self.raw_store.prune_processed(self.repo)
        self.artifact_store.prune_archive()

        logger.info(
            f"[Orchestrator] Run {run_id} complete in {duration:.2f}s — "
            f"Ingest: {results['ok']} ok / {results['err']} err, "
            f"Routes: {build_ok} ok / {build_err} err. "
            f"(ingest {ingest_duration:.1f}s, transform {transform_duration:.1f}s, build {build_duration:.1f}s)"
        )
