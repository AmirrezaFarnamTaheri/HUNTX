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
    """One content-addressed configuration produced by the Go collector."""

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
        """Return an async/sync-compatible iterator over the current scrape."""
        return AsyncSyncIterator(self._list_new_async(state))

    def _subprocess_timeout(self) -> float | None:
        """Return a subprocess budget bounded by the orchestrator deadline."""
        cap = 300.0
        if self.deadline is None:
            return cap
        remaining = float(self.deadline) - time.time()
        if remaining <= 0:
            return None
        return max(0.1, min(cap, remaining))

    async def _list_new_async(self, state: Optional[Dict[str, Any]]):
        import asyncio
        import shutil

        del state
        loop = asyncio.get_running_loop()

        def run_scraper_sync():
            output_file = os.path.join(self.base_dir, "collected_configs.txt")
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError as exc:
                    logger.warning("Could not remove existing configs file: %s", exc)

            go_binary = shutil.which("go")
            if not go_binary:
                logger.error(
                    "Go binary ('go') not found in system PATH. "
                    "Install Go to run v2ray_collector."
                )
                return []

            timeout = self._subprocess_timeout()
            if timeout is None:
                logger.warning("Skipping Go collector because the run deadline is exhausted")
                return []

            logger.info("Executing Go scraper package in %s...", self.base_dir)
            try:
                result = subprocess.run(
                    [go_binary, "run", "."],
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                # Do not log raw stdout/stderr: share URIs frequently embed
                # usernames, UUIDs, passwords and other credentials. Preserve
                # only bounded diagnostic shape here.
                if result.stdout:
                    logger.debug(
                        "Go scraper produced %s stdout byte(s)",
                        len(result.stdout.encode("utf-8", errors="ignore")),
                    )
                if result.stderr:
                    logger.warning(
                        "Go scraper produced %s stderr byte(s)",
                        len(result.stderr.encode("utf-8", errors="ignore")),
                    )
                if result.returncode != 0:
                    logger.error("Go scraper exited with status %s", result.returncode)
                    return []
            except subprocess.TimeoutExpired:
                logger.error("Go scraper exceeded its %.2fs run budget", timeout)
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
        """Return connector state persisted by the ingestion pipeline."""
        return {"last_run_time": self.last_run_time}
