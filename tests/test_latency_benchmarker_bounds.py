from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from huntx.core.latency_benchmarker import filter_proxies_by_latency


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"concurrency": 0},
        {"concurrency": True},
        {"concurrency": 1001},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"max_latency_ms": 0},
        {"max_latency_ms": float("inf")},
    ],
)
async def test_latency_filter_rejects_invalid_resource_settings(kwargs):
    with pytest.raises(ValueError):
        await filter_proxies_by_latency(
            [{"data": {"line": "vless://user@example.com:443"}}],
            **kwargs,
        )


@pytest.mark.asyncio
async def test_latency_filter_uses_fixed_worker_bound_and_preserves_order():
    proxies = [
        {"id": index, "data": {"line": f"vless://user@host{index}.example:443"}}
        for index in range(12)
    ]
    active = 0
    peak = 0

    async def fake_probe(_url: str, timeout: float):
        nonlocal active, peak
        assert timeout == 1.0
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return 10.0

    with patch(
        "huntx.core.latency_benchmarker.check_proxy_latency",
        side_effect=fake_probe,
    ):
        result = await filter_proxies_by_latency(
            proxies,
            concurrency=2,
            timeout=1.0,
            max_latency_ms=100.0,
        )

    assert peak <= 2
    assert peak >= 1
    assert [record["id"] for record in result] == list(range(12))
