import logging
from typing import List, Dict, Any
from ..state.repo import StateRepo
from ..store.artifact_store import ArtifactStore
from ..formats.registry import FormatRegistry

logger = logging.getLogger(__name__)

class BuildPipeline:
    def __init__(self, state_repo: StateRepo, artifact_store: ArtifactStore, registry: FormatRegistry):
        self.state_repo = state_repo
        self.artifact_store = artifact_store
        self.registry = registry

    def run(self, route_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds artifact for a specific route.
        """
        route_name = route_config["name"]
        formats = route_config["formats"] # e.g. ["npvt"]
        allowed_source_ids = route_config.get("from_sources", [])

        # 1. Fetch records
        records = self.state_repo.get_records_for_build(formats, allowed_source_ids)
        if not records:
            return None

        # 2. Build using the PRIMARY format handler
        primary_fmt = formats[0]
        handler = self.registry.get(primary_fmt)

        try:
            artifact_bytes = handler.build(records)

            # 3. Save artifact
            artifact_hash = self.artifact_store.save_artifact(route_name, artifact_bytes)

            return {
                "route_name": route_name,
                "artifact_hash": artifact_hash,
                "data": artifact_bytes,
                "count": len(records)
            }
        except Exception as e:
            logger.exception(f"Build failed for {route_name}")
            return None
