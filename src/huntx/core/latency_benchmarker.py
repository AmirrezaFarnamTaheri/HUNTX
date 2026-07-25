"""
Async Proxy Latency Benchmarker module for HuntX.
Tests proxy endpoint reachability and latency via socket / HTTP probes.
"""
<<<<<<< Updated upstream
import asyncio
import socket
=======

import asyncio
>>>>>>> Stashed changes
import time
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


async def check_proxy_latency(proxy_url: str, timeout: float = 3.0) -> Optional[float]:
    """
    Measures TCP connection latency to the host:port of a proxy URI.
    Returns latency in milliseconds if reachable, or None if failed/timed out.
    """
    try:
        if not proxy_url or not isinstance(proxy_url, str):
            return None

        # Basic parse host and port from proxy URI
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port

        if not host:
            # Fallback for URIs without standard scheme format
            parts = proxy_url.replace("//", "").split("@")[-1].split(":")
            if len(parts) >= 2:
                host = parts[0]
                try:
                    port = int(parts[1].split("/")[0].split("?")[0].split("#")[0])
                except ValueError:
                    port = None

        if not host or not port:
            return None

        start_time = time.monotonic()
        # Non-blocking async TCP connection attempt
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        elapsed_ms = (time.monotonic() - start_time) * 1000.0

<<<<<<< Updated upstream
        res = writer.close()
        if asyncio.iscoroutine(res):
=======
        res: Any = writer.close()  # type: ignore[func-returns-value]
        if res is not None and asyncio.iscoroutine(res):
>>>>>>> Stashed changes
            await res
        if hasattr(writer, "wait_closed"):
            res_wait = writer.wait_closed()
            if asyncio.iscoroutine(res_wait):
                await res_wait
        return elapsed_ms
    except Exception:
        return None


async def filter_proxies_by_latency(
    proxies: List[Dict[str, Any]],
    max_latency_ms: float = 3000.0,
    concurrency: int = 50,
    timeout: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Filters a list of proxy dict records by latency.
    Only proxies under max_latency_ms are retained.
    """
    if not proxies:
        return []

    semaphore = asyncio.Semaphore(concurrency)

    async def _worker(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        line = record.get("data", {}).get("line", "") or record.get("line", "")
        async with semaphore:
            latency = await check_proxy_latency(line, timeout=timeout)
            if latency is not None and latency <= max_latency_ms:
                res = dict(record)
                if "data" in res and isinstance(res["data"], dict):
                    res["data"]["latency_ms"] = round(latency, 2)
                else:
                    res["latency_ms"] = round(latency, 2)
                return res
            return None

    tasks = [_worker(p) for p in proxies]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_proxies = [r for r in results if isinstance(r, dict)]
    logger.info("Latency Benchmarker: %d/%d proxies passed latency filter", len(valid_proxies), len(proxies))
    return valid_proxies
