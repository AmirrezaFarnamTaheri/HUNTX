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

    def run(self, route_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Builds artifacts for a specific route (one per format).
        """
        route_name = route_config["name"]
        formats = route_config["formats"] # e.g. ["npvt", "ovpn"]
        allowed_source_ids = route_config.get("from_sources", [])

        results = []

        for fmt in formats:
            # 1. Fetch records for this format
            records = self.state_repo.get_records_for_build([fmt], allowed_source_ids)
            if not records:
                continue

            # 2. Build using the format handler
            handler = self.registry.get(fmt)
            if not handler:
                logger.warning(f"No handler for format {fmt}")
                continue

            try:
                artifact_bytes = handler.build(records)

                # 3. Save artifact
                artifact_hash = self.artifact_store.save_artifact(route_name, artifact_bytes)

                results.append({
                    "route_name": route_name,
                    "format": fmt,
                    "artifact_hash": artifact_hash,
                    "data": artifact_bytes,
                    "count": len(records)
                })
            except Exception as e:
                logger.exception(f"Build failed for {route_name} format {fmt}")

        return results
