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
        Builds artifacts for a specific route across all requested formats.
        Returns a list of build results (one per format).
        """
        route_name = route_config["name"]
        formats = route_config["formats"] # e.g. ["npvt", "conf_lines"]
        allowed_source_ids = route_config.get("from_sources", [])

        logger.info(f"Starting build for route '{route_name}' (formats: {formats})")

        # 1. Fetch records
        # Note: We fetch records compatible with ANY of the formats.
        # Typically the registry handlers know how to convert/filter.
        # Ideally, we should fetch based on what the handlers need, but for now assuming
        # handlers work on a common record structure or we fetch all relevant types.
        # Since 'get_records_for_build' takes format IDs, we pass all of them.
        records = self.state_repo.get_records_for_build(formats, allowed_source_ids)
        record_count = len(records)
        logger.info(f"Fetched {record_count} records for route '{route_name}'")

        if not records:
            logger.info(f"No records found for route '{route_name}', skipping build.")
            return []

        results = []

        # 2. Build for EACH format
        for fmt in formats:
            try:
                logger.debug(f"Building format '{fmt}' for route '{route_name}'")
                handler = self.registry.get(fmt)
                if not handler:
                    logger.error(f"No handler for format {fmt}, skipping.")
                    continue

                artifact_bytes = handler.build(records)

                if not artifact_bytes:
                     logger.warning(f"Build returned empty artifact for '{route_name}' format '{fmt}'")
                     continue

                # 3. Save artifact
                # Save to history (hashed)
                artifact_hash = self.artifact_store.save_artifact(route_name, artifact_bytes)
                logger.debug(f"Saved artifact history: {artifact_hash} ({len(artifact_bytes)} bytes)")

                # Save to output (named)
                self.artifact_store.save_output(route_name, fmt, artifact_bytes)
                logger.info(f"Saved output artifact: {route_name} ({fmt})")

                # Unique ID for state tracking combines route and format
                unique_id = f"{route_name}:{fmt}"

                results.append({
                    "route_name": route_name,
                    "format": fmt,
                    "unique_id": unique_id,
                    "artifact_hash": artifact_hash,
                    "data": artifact_bytes,
                    "count": len(records)
                })
            except Exception as e:
                logger.exception(f"Build failed for {route_name} format {fmt}: {e}")

        logger.info(f"Build complete for route '{route_name}': {len(results)} formats built.")
        return results
