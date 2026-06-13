from __future__ import annotations

import os
import subprocess
import time
import logging
import hashlib
from typing import Dict, Any, Iterator, Optional
from ..base import SourceConnector, SourceItem, AsyncSyncIterator

logger = logging.getLogger("huntx.connectors.v2ray_collector")


class V2RayCollectorItem:
    __slots__ = ("external_id", "data", "metadata")

    def __init__(self, external_id: str, data: bytes, metadata: Dict[str, Any]):
        self.external_id = external_id
        self.data = data
        self.metadata = metadata


class V2RayCollectorConnector(SourceConnector):
    """
    Python wrapper connector for the Go v2ray_collector scraper (smgo).
    Executes 'go run main.go' to fetch configurations from Telegram and
    ingests the results.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = base_dir
        self.last_run_time = 0

    def list_new(self, state: Optional[Dict[str, Any]] = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: Optional[Dict[str, Any]]):
        import asyncio
        loop = asyncio.get_running_loop()

        def run_scraper_sync():
            output_file = os.path.join(self.base_dir, "collected_configs.txt")
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError as e:
                    logger.warning(f"Could not remove existing configs file: {e}")

            # 2. Run the Go scraper
            import shutil
            if not shutil.which("go"):
                logger.error("Go binary ('go') not found in system PATH. Please install Go toolchain to run v2ray_collector.")
                return []

            logger.info(f"Executing Go scraper in {self.base_dir}...")
            try:
                res = subprocess.run(
                    ["go", "run", "main.go"],
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300  # 5 minutes safety limit
                )
                if res.stdout:
                    logger.debug(f"Go scraper stdout: {res.stdout}")
                if res.stderr:
                    logger.warning(f"Go scraper stderr: {res.stderr}")
            except Exception as e:
                logger.error(f"Failed to execute Go scraper subprocess: {e}")
                return []

            # 3. Read the output file
            if not os.path.exists(output_file):
                logger.warning(f"Scraper completed but no output file was written at {output_file}")
                return []

            try:
                with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.readlines()
            except Exception as e:
                logger.error(f"Failed to read output file: {e}")
                return []

        lines = await loop.run_in_executor(None, run_scraper_sync)
        logger.info(f"Go scraper completed. Scraped {len(lines)} configs.")

        # 4. Yield each config line as a SourceItem
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # Stable unique external ID derived from line content
            h = hashlib.sha256(line.encode('utf-8')).hexdigest()[:16]
            ext_id = f"goscrap_{h}_{idx}"
            
            yield V2RayCollectorItem(
                external_id=ext_id,
                data=line.encode('utf-8'),
                metadata={"filename": "collected_configs.txt", "is_text": True}
            )

        self.last_run_time = int(time.time())


    def get_state(self) -> Dict[str, Any]:
        return {"last_run_time": self.last_run_time}
