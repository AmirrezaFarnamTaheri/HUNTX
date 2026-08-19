"""Async reachability/latency probes for validated public proxy endpoints."""

import asyncio
import ipaddress
import logging
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _public_addresses(address_info: list[tuple[Any, ...]]) -> list[tuple[int, str]]:
    """Return unique globally routable resolved addresses with their families."""
    result: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for entry in address_info:
        if len(entry) < 5:
            continue
        family = int(entry[0])
        sockaddr = entry[4]
        if not sockaddr:
            continue
        raw_address = str(sockaddr[0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            continue
        if not address.is_global:
            logger.warning(
                "Latency Benchmarker rejected non-public resolved address %s",
                address,
            )
            continue
        key = (family, str(address))
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


async def check_proxy_latency(proxy_url: str, timeout: float = 3.0) -> Optional[float]:
    """Measure TCP latency without allowing probes into private address space.

    The endpoint hostname is resolved once, every candidate address is checked
    with :mod:`ipaddress`, and the connection is made to the accepted numeric
    address rather than resolving the attacker-controlled hostname again.  This
    prevents loopback/private/link-local/reserved DNS answers and DNS rebinding
    from turning the benchmark helper into an internal port scanner.
    """
    try:
        if not proxy_url or not isinstance(proxy_url, str) or timeout <= 0:
            return None

        parsed = urlparse(proxy_url)
        host = parsed.hostname
        try:
            port = parsed.port
        except ValueError:
            return None

        if not host:
            parts = proxy_url.replace("//", "").split("@")[-1].split(":")
            if len(parts) >= 2:
                host = parts[0]
                try:
                    port = int(parts[1].split("/")[0].split("?")[0].split("#")[0])
                except ValueError:
                    port = None

        if not host or not port or not 1 <= int(port) <= 65535:
            return None

        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + timeout
        address_info = await asyncio.wait_for(
            loop.getaddrinfo(
                host,
                int(port),
                type=socket.SOCK_STREAM,
            ),
            timeout=timeout,
        )
        candidates = _public_addresses(address_info)
        if not candidates:
            return None

        for family, address in candidates:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            start_time = time.monotonic()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        address,
                        int(port),
                        family=family,
                    ),
                    timeout=remaining,
                )
            except (OSError, asyncio.TimeoutError):
                continue
            del reader
            elapsed_ms = (time.monotonic() - start_time) * 1000.0

            result: Any = writer.close()  # type: ignore[func-returns-value]
            if result is not None and asyncio.iscoroutine(result):
                await result
            if hasattr(writer, "wait_closed"):
                wait_result = writer.wait_closed()
                if asyncio.iscoroutine(wait_result):
                    await wait_result
            return elapsed_ms
        return None
    except Exception:
        return None


def _extract_proxy_uri(record: Dict[str, Any]) -> str:
    """Extract a proxy URI from mapping-, text-, or byte-backed records."""
    data = record.get("data")
    if isinstance(data, dict):
        for key in ("line", "raw_uri", "uri"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    elif isinstance(data, str):
        if data:
            return data
    elif isinstance(data, (bytes, bytearray, memoryview)):
        value = bytes(data).decode("utf-8", errors="ignore").strip()
        if value:
            return value

    for key in ("raw_uri", "line", "uri"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


async def filter_proxies_by_latency(
    proxies: List[Dict[str, Any]],
    max_latency_ms: float = 3000.0,
    concurrency: int = 50,
    timeout: float = 2.0,
) -> List[Dict[str, Any]]:
    """Return only proxy records that complete a public-endpoint probe in time."""
    if not proxies:
        return []

    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def _worker(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        line = _extract_proxy_uri(record)
        async with semaphore:
            latency = await check_proxy_latency(line, timeout=timeout)
            if latency is not None and latency <= max_latency_ms:
                result = dict(record)
                if "data" in result and isinstance(result["data"], dict):
                    result["data"] = dict(result["data"])
                    result["data"]["latency_ms"] = round(latency, 2)
                else:
                    result["latency_ms"] = round(latency, 2)
                return result
            return None

    tasks = [_worker(proxy) for proxy in proxies]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_proxies = [result for result in results if isinstance(result, dict)]
    logger.info(
        "Latency Benchmarker: %d/%d proxies passed latency filter",
        len(valid_proxies),
        len(proxies),
    )
    return valid_proxies
