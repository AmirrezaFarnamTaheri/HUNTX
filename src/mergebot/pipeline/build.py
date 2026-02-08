import base64
import json
import logging
import time
from typing import List, Dict, Any
from ..state.repo import StateRepo
from ..store.artifact_store import ArtifactStore
from ..formats.registry import FormatRegistry

logger = logging.getLogger(__name__)

# Proxy URI schemes that carry V2Ray-compatible configs
_PROXY_SCHEMES = ("vmess://", "vless://", "trojan://", "ss://", "ssr://")


class BuildPipeline:
    def __init__(self, state_repo: StateRepo, artifact_store: ArtifactStore, registry: FormatRegistry):
        self.state_repo = state_repo
        self.artifact_store = artifact_store
        self.registry = registry

    # ------------------------------------------------------------------
    # V2Ray link decoder (artifact-only, never sent to bot)
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_v2ray_links(artifact_bytes: bytes) -> bytes:
        """Decode proxy URI lines into a human-readable JSON artifact."""
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return b""

        decoded_entries: List[Dict[str, Any]] = []
        protocols: Dict[str, int] = {}

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            protocol = None
            entry = None

            if line.startswith("vmess://"):
                protocol = "vmess"
                try:
                    b64 = line[8:] # len("vmess://") is 8
                    padding = 4 - len(b64) % 4
                    if padding != 4:
                        b64 += "=" * padding
                    raw = base64.b64decode(b64).decode("utf-8", errors="ignore")
                    obj = json.loads(raw)
                    entry = {"protocol": "vmess", "decoded": obj, "raw": line}
                except Exception:
                    entry = {"protocol": "vmess", "raw": line, "error": "decode_failed"}
            elif line.startswith("vless://"):
                protocol = "vless"
                entry = {"protocol": "vless", "raw": line}
            elif line.startswith("trojan://"):
                protocol = "trojan"
                entry = {"protocol": "trojan", "raw": line}
            elif line.startswith("ss://"):
                protocol = "shadowsocks"
                entry = {"protocol": "shadowsocks", "raw": line}
            elif line.startswith("ssr://"):
                protocol = "shadowsocksr"
                entry = {"protocol": "shadowsocksr", "raw": line}

            if entry:
                decoded_entries.append(entry)
                protocols[protocol] = protocols.get(protocol, 0) + 1

        if not decoded_entries:
            return b""

        result: Dict[str, Any] = {
            "total": len(decoded_entries),
            "protocols": protocols,
            "entries": decoded_entries,
        }

        return json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")

    # ------------------------------------------------------------------

    def run(self, route_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build artifacts for a route. Returns list of build results (one per format)."""
        route_name = route_config["name"]
        formats = route_config["formats"]
        allowed_source_ids = route_config.get("from_sources", [])

        logger.info(f"[Build] Route '{route_name}' — formats={formats}, sources={len(allowed_source_ids)}")

        fetch_start = time.time()
        records = self.state_repo.get_records_for_build(formats, allowed_source_ids)
        fetch_duration = time.time() - fetch_start
        record_count = len(records)

        unique_sources = {r.get("source_id") for r in records if r.get("source_id")}
        logger.info(
            f"[Build] Fetched {record_count} records in {fetch_duration:.2f}s " f"({len(unique_sources)} sources)"
        )

        if not records:
            logger.info(f"[Build] No records for route '{route_name}'.")
            return []

        results: List[Dict[str, Any]] = []

        for fmt in formats:
            try:
                build_start = time.time()
                handler = self.registry.get(fmt)
                if not handler:
                    logger.error(f"[Build] No handler for format {fmt}, skipping.")
                    continue

                artifact_bytes = handler.build(records)
                build_duration = time.time() - build_start
                artifact_size_kb = len(artifact_bytes) / 1024

                if not artifact_bytes:
                    logger.warning(f"[Build] Empty artifact for '{route_name}' format '{fmt}'")
                    continue

                artifact_hash = self.artifact_store.save_artifact(route_name, fmt, artifact_bytes)
                self.artifact_store.save_output(route_name, fmt, artifact_bytes)
                logger.info(
                    f"[Build] {route_name}/{fmt}: {artifact_size_kb:.1f} KB, "
                    f"{build_duration:.2f}s, hash={artifact_hash[:12] if artifact_hash else 'N/A'}"
                )

                # Decode V2Ray links → local artifact (never published to bot)
                if fmt in ("npvt", "npvtsub"):
                    decoded = self._decode_v2ray_links(artifact_bytes)
                    if decoded:
                        self.artifact_store.save_output(route_name, f"{fmt}.decoded.json", decoded)
                        logger.info(f"[Build] Saved decoded V2Ray artifact for {route_name}/{fmt}")

                unique_id = f"{route_name}:{fmt}"
                results.append(
                    {
                        "route_name": route_name,
                        "format": fmt,
                        "unique_id": unique_id,
                        "artifact_hash": artifact_hash,
                        "data": artifact_bytes,
                        "count": record_count,
                    }
                )
            except Exception as e:
                logger.exception(f"[Build] Failed for {route_name}/{fmt}: {e}")

        logger.info(f"[Build] Route '{route_name}': {len(results)} format(s) built.")
        return results
