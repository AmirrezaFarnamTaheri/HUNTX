from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional

from ..base import AsyncSyncIterator, SourceConnector

logger = logging.getLogger("huntx.connectors.v2ray_collector")


class V2RayCollectorItem:
    __slots__ = ("external_id", "data", "metadata")

    def __init__(self, external_id: str, data: bytes, metadata: Dict[str, Any]):
        self.external_id = external_id
        self.data = data
        self.metadata = metadata


class V2RayCollectorConnector(SourceConnector):
    """Python wrapper for the Go v2ray_collector scraper."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = base_dir
        self.last_run_time = 0
        self.deadline: Optional[float] = None

    @staticmethod
    def build_external_id(line: str) -> str:
        """Return a stable content identity independent of output ordering.

        Historical versions used ``sha256[:16]`` and later ``sha256[:32]``
        plus the scraper's line index. Reordering the same scraper output could
        therefore manufacture a new identity. New identities use the complete
        SHA-256 digest and intentionally omit the volatile index.
        """
        digest = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
        return f"goscrap_{digest}"

    def list_new(self, state: Optional[Dict[str, Any]] = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: Optional[Dict[str, Any]]):
        import asyncio
        import shutil

        loop = asyncio.get_running_loop()

        def run_scraper_sync():
            output_file = os.path.join(self.base_dir, "collected_configs.txt")
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError as exc:
                    logger.warning("Could not remove existing configs file: %s", exc)

            if not shutil.which("go"):
                logger.error(
                    "Go binary ('go') not found in system PATH. "
                    "Install Go to run v2ray_collector."
                )
                return []

            logger.info("Executing Go scraper in %s...", self.base_dir)
            try:
                result = subprocess.run(
                    ["go", "run", "main.go"],
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300,
                    check=False,
                )
                if result.stdout:
                    logger.debug("Go scraper stdout: %s", result.stdout)
                if result.stderr:
                    logger.warning("Go scraper stderr: %s", result.stderr)
                if result.returncode != 0:
                    logger.error("Go scraper exited with status %s", result.returncode)
                    return []
            except (OSError, subprocess.SubprocessError) as exc:
                logger.error("Failed to execute Go scraper subprocess: %s", exc)
                return []

            if not os.path.exists(output_file):
                logger.warning(
                    "Scraper completed but no output file was written at %s",
                    output_file,
                )
                return []

            try:
                with open(output_file, "r", encoding="utf-8", errors="ignore") as stream:
                    return stream.readlines()
            except OSError as exc:
                logger.error("Failed to read output file: %s", exc)
                return []

        lines = await loop.run_in_executor(None, run_scraper_sync)
        logger.info("Go scraper completed. Scraped %s configs.", len(lines))

        yielded_ids: set[str] = set()
        for line in lines:
            line = line.strip()
            if not line:
                continue

            ext_id = self.build_external_id(line)
            if ext_id in yielded_ids:
                continue
            yielded_ids.add(ext_id)

            yield V2RayCollectorItem(
                external_id=ext_id,
                data=line.encode("utf-8"),
                metadata={
                    "filename": "collected_configs.txt",
                    "is_text": True,
                    # Ingestion uses this opt-in to recognize rows written by
                    # the old index-dependent external-ID schemes via raw_hash.
                    "dedupe_by_content": True,
                },
            )

        self.last_run_time = int(time.time())

    def get_state(self) -> Dict[str, Any]:
        return {"last_run_time": self.last_run_time}
