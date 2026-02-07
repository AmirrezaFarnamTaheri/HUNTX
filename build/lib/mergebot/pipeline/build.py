import logging
import time
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

        logger.info(f"[Build] Starting build for route '{route_name}' (formats: {formats}, sources: {allowed_source_ids})")

        # 1. Fetch records
        # Note: We fetch records compatible with ANY of the formats.
        fetch_start = time.time()
        records = self.state_repo.get_records_for_build(formats, allowed_source_ids)
        fetch_duration = time.time() - fetch_start
        record_count = len(records)
        logger.info(f"[Build] Fetched {record_count} records for route '{route_name}' in {fetch_duration:.2f}s")

        if not records:
            logger.info(f"[Build] No records found for route '{route_name}', skipping build.")
            return []

        results = []

        # 2. Build for EACH format
        for fmt in formats:
            try:
                build_start = time.time()
                logger.debug(f"[Build] Building format '{fmt}' for route '{route_name}' using {record_count} records")
                handler = self.registry.get(fmt)
                if not handler:
                    logger.error(f"[Build] No handler for format {fmt}, skipping.")
                    continue

                artifact_bytes = handler.build(records)
                build_duration = time.time() - build_start
                artifact_size = len(artifact_bytes)

                if not artifact_bytes:
                     logger.warning(f"[Build] Build returned empty artifact for '{route_name}' format '{fmt}'")
                     continue

                # 3. Save artifact
                # Save to history (hashed)
                artifact_hash = self.artifact_store.save_artifact(route_name, artifact_bytes)
                logger.debug(f"[Build] Saved artifact history: {artifact_hash} ({artifact_size} bytes)")

                # Save to output (named)
                self.artifact_store.save_output(route_name, fmt, artifact_bytes)
                logger.info(f"[Build] Saved output artifact: {route_name} ({fmt}) - Size: {artifact_size} bytes, Time: {build_duration:.2f}s, Hash: {artifact_hash}")

                # Unique ID for state tracking combines route and format
                unique_id = f"{route_name}:{fmt}"

                results.append({
                    "route_name": route_name,
                    "format": fmt,
                    "unique_id": unique_id,
                    "artifact_hash": artifact_hash,
                    "data": artifact_bytes,
                    "count": record_count
                })
            except Exception as e:
                logger.exception(f"[Build] Build failed for {route_name} format {fmt}: {e}")

        logger.info(f"[Build] Build complete for route '{route_name}': {len(results)} formats built.")
        return results
