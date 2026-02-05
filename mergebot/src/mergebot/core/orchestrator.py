import logging
from ..store.paths import STATE_DB_PATH
from ..store.raw_store import RawStore
from ..store.artifact_store import ArtifactStore
from ..state.db import open_db
from ..state.repo import StateRepo
from ..formats.registry import FormatRegistry
from ..formats.register_builtin import register_all_formats
from ..connectors.telegram.connector import TelegramConnector
from ..pipeline.ingest import IngestionPipeline
from ..pipeline.transform import TransformPipeline
from ..pipeline.build import BuildPipeline
from ..pipeline.publish import PublishPipeline
from ..config.schema import AppConfig

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, config: AppConfig):
        self.config = config

        # Init stores
        self.raw_store = RawStore()
        self.artifact_store = ArtifactStore()

        # Init DB/Repo
        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        # Init Registry
        self.registry = FormatRegistry.get_instance()
        register_all_formats(self.registry, self.raw_store)

        # Map source configs for TransformPipeline
        source_configs = {s.id: s for s in self.config.sources}

        # Init Pipelines
        self.ingest_pipeline = IngestionPipeline(self.raw_store, self.repo)
        self.transform_pipeline = TransformPipeline(self.raw_store, self.repo, self.registry, source_configs)
        self.build_pipeline = BuildPipeline(self.repo, self.artifact_store, self.registry)
        self.publish_pipeline = PublishPipeline(self.repo)

    def run(self):
        logger.info("Starting run...")

        # 1. Ingest
        for src_conf in self.config.sources:
            if src_conf.type == "telegram" and src_conf.telegram:
                conn = TelegramConnector(
                    token=src_conf.telegram.token,
                    chat_id=src_conf.telegram.chat_id,
                    state=self.repo.get_source_state(src_conf.id)
                )
                try:
                    self.ingest_pipeline.run(src_conf.id, conn)
                except Exception:
                    logger.exception(f"Ingest failed for {src_conf.id}")

        # 2. Transform
        try:
            self.transform_pipeline.process_pending()
        except Exception:
            logger.exception("Transform failed")

        # 3. Build & Publish
        for route in self.config.routes:
            try:
                # Pass from_sources to BuildPipeline
                route_dict = {
                    "name": route.name,
                    "formats": route.formats,
                    "from_sources": route.from_sources
                }

                result = self.build_pipeline.run(route_dict)
                if result:
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
                    self.publish_pipeline.run(result, dests)
            except Exception:
                logger.exception(f"Build/Publish failed for {route.name}")

        logger.info("Run complete.")
