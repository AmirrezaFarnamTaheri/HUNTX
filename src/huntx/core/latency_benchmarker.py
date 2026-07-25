"""Bounded asynchronous reachability and latency probes for proxy records."""

import asyncio
import inspect
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def check_proxy_latency(proxy_url: str, timeout: float = 3.0) -> Optional[float]:
    """Return TCP connection latency in milliseconds, or ``None`` on probe failure."""
    if not isinstance(proxy_url, str) or not proxy_url or timeout <= 0:
        return None

    writer: Any = None
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port

        if not host:
            parts = proxy_url.replace("//", "").split("@")[-1].split(":")
            if len(parts) >= 2:
                host = parts[0]
                try:
                    port = int(parts[1].split("/")[0].split("?")[0].split("#")[0])
                except ValueError:
                    port = None

        if not host or not port:
            return None

        started_at = time.monotonic()
        connection = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(connection, timeout=timeout)
        return (time.monotonic() - started_at) * 1000.0
    except (asyncio.TimeoutError, OSError, ValueError):
        return None
    finally:
        if writer is not None:
            writer.close()
            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                try:
                    result = wait_closed()
                    if inspect.isawaitable(result):
                        await result
                except (OSError, RuntimeError):
                    logger.debug("Proxy connection cleanup failed", exc_info=True)


async def filter_proxies_by_latency(
    proxies: List[Dict[str, Any]],
    max_latency_ms: float = 3000.0,
    concurrency: int = 50,
    timeout: float = 2.0,
    retries: int = 0,
    retry_backoff: float = 0.1,
) -> List[Dict[str, Any]]:
    """Return reachable proxies within the latency budget using bounded probes.

    Each probe has its own timeout. At most ``concurrency`` probes run at once,
    retries are bounded, and cancellation of the caller cancels the gathered
    work rather than leaving background probes running.
    """
    if not proxies:
        return []
    if max_latency_ms < 0:
        raise ValueError("max_latency_ms must be non-negative")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if retries < 0:
        raise ValueError("retries must be non-negative")
    if retry_backoff < 0:
        raise ValueError("retry_backoff must be non-negative")

    semaphore = asyncio.Semaphore(concurrency)

    async def _worker(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = record.get("data")
        line = (data.get("line", "") if isinstance(data, dict) else "") or record.get("line", "")
        if not isinstance(line, str) or not line:
            return None

        latency: Optional[float] = None
        async with semaphore:
            for attempt in range(retries + 1):
                latency = await check_proxy_latency(line, timeout=timeout)
                if latency is not None:
                    break
                if attempt < retries and retry_backoff:
                    await asyncio.sleep(retry_backoff * (2**attempt))

        if latency is None or latency > max_latency_ms:
            return None

        result = dict(record)
        if isinstance(data, dict):
            result["data"] = dict(data)
            result["data"]["latency_ms"] = round(latency, 2)
        else:
            result["latency_ms"] = round(latency, 2)
        return result

    results = await asyncio.gather(*(_worker(proxy) for proxy in proxies))
    valid_proxies = [result for result in results if result is not None]
    logger.info("Latency Benchmarker: %d/%d proxies passed latency filter", len(valid_proxies), len(proxies))
    return valid_proxies
