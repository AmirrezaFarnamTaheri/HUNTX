import logging
import time
from ..store.paths import STATE_DB_PATH
from ..store.raw_store import RawStore
from ..store.artifact_store import ArtifactStore
from ..state.db import open_db
from ..state.repo import StateRepo
from ..formats.registry import FormatRegistry
from ..formats.register_builtin import register_all_formats
from ..connectors.telegram.connector import TelegramConnector
from ..connectors.telegram_user.connector import TelegramUserConnector
from ..pipeline.ingest import IngestionPipeline
from ..pipeline.transform import TransformPipeline
from ..pipeline.build import BuildPipeline
from ..pipeline.publish import PublishPipeline
from ..config.schema import AppConfig

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, config: AppConfig):
        logger.info("Initializing Orchestrator...")
        self.config = config

        # Init stores
        self.raw_store = RawStore()
        self.artifact_store = ArtifactStore()

        # Init DB/Repo
        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)
        logger.debug(f"Connected to state DB at {STATE_DB_PATH}")

        # Init Registry
        self.registry = FormatRegistry.get_instance()
        register_all_formats(self.registry, self.raw_store)
        logger.debug("Formats registered.")

        # Map source configs for TransformPipeline
        source_configs = {s.id: s for s in self.config.sources}

        # Init Pipelines
        self.ingest_pipeline = IngestionPipeline(self.raw_store, self.repo)
        self.transform_pipeline = TransformPipeline(self.raw_store, self.repo, self.registry, source_configs)
        self.build_pipeline = BuildPipeline(self.repo, self.artifact_store, self.registry)
        self.publish_pipeline = PublishPipeline(self.repo)
        logger.info("Pipelines initialized.")

    def run(self):
        start_time = time.time()
        logger.info("Starting orchestrator run...")

        # 1. Ingest
        ingest_count = 0
        for src_conf in self.config.sources:
            if src_conf.type == "telegram" and src_conf.telegram:
                logger.info(f"Running ingestion for source: {src_conf.id}")
                conn = TelegramConnector(
                    token=src_conf.telegram.token,
                    chat_id=src_conf.telegram.chat_id,
                    state=self.repo.get_source_state(src_conf.id)
                )
                try:
                    self.ingest_pipeline.run(src_conf.id, conn, source_type=src_conf.type)
                    ingest_count += 1
                except Exception as e:
                    logger.exception(f"Ingest failed for source '{src_conf.id}': {e}")
            elif src_conf.type == "telegram_user" and src_conf.telegram_user:
                logger.info(f"Running ingestion for source: {src_conf.id} (Telegram User)")
                conn = TelegramUserConnector(
                    api_id=src_conf.telegram_user.api_id,
                    api_hash=src_conf.telegram_user.api_hash,
                    session=src_conf.telegram_user.session,
                    peer=src_conf.telegram_user.peer,
                    state=self.repo.get_source_state(src_conf.id)
                )
                try:
                    self.ingest_pipeline.run(src_conf.id, conn, source_type=src_conf.type)
                    ingest_count += 1
                except Exception as e:
                    logger.exception(f"Ingest failed for source '{src_conf.id}': {e}")
            else:
                logger.warning(f"Skipping source '{src_conf.id}': Unsupported type or missing config.")

        # 2. Transform
        try:
            logger.info("Running transformation pipeline...")
            self.transform_pipeline.process_pending()
        except Exception as e:
            logger.exception(f"Transform pipeline failed: {e}")

        # 3. Build & Publish
        build_publish_count = 0
        for route in self.config.routes:
            logger.info(f"Processing route: {route.name}")
            try:
                # Pass from_sources to BuildPipeline
                route_dict = {
                    "name": route.name,
                    "formats": route.formats,
                    "from_sources": route.from_sources
                }

                # Build returns a list of results (one per format)
                results = self.build_pipeline.run(route_dict)

                if results:
                    # Convert destination objects to dicts
                    dests = [
                        {
                            "chat_id": d.chat_id,
                            "mode": d.mode,
                            "caption_template": d.caption_template,
                            "token": d.token
                        }
                        for d in route.destinations
                    ]

                    # Publish each result
                    for res in results:
                        self.publish_pipeline.run(res, dests)

                    build_publish_count += 1

            except Exception as e:
                logger.exception(f"Build/Publish failed for route '{route.name}': {e}")

        duration = time.time() - start_time
        logger.info(f"Orchestrator run complete in {duration:.2f}s. Sources ingested: {ingest_count}, Routes processed: {build_publish_count}.")
