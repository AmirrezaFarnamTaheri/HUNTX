# tests/perf/test_transform_bench.py
"""
Throughput benchmark for TransformPipeline._process_single_file.
Run with: pytest tests/perf/test_transform_bench.py -m perf -v
"""
import time
import pytest
from unittest.mock import MagicMock
from huntx.utils.profiler import wall_clock

SAMPLE_DATA = (
    b"vless://abc@192.0.2.1:443?security=tls&sni=example.com#t\n" * 200
)
N = 100


@pytest.mark.perf
def test_process_single_file_under_5ms_average():
    """Each file must process in < 5 ms on average (single-threaded)."""
    from huntx.pipeline.transform import TransformPipeline
    from huntx.formats.registry import FormatRegistry
    from huntx.formats.register_builtin import register_all_formats

    raw_store = MagicMock()
    raw_store.get.return_value = SAMPLE_DATA
    state_repo = MagicMock()

    registry = FormatRegistry()
    register_all_formats(registry, raw_store)

    pipeline = TransformPipeline(
        raw_store, state_repo, registry, {}, max_workers=4
    )

    rows = [
        {"raw_hash": "a" * 64, "source_id": "s1", "filename": f"file_{i}.txt"}
        for i in range(N)
    ]

    _, elapsed = wall_clock(
        lambda: [pipeline._process_single_file(r) for r in rows]
    )

    avg_ms = (elapsed / N) * 1000
    assert avg_ms < 10.0, (
        f"Average per-file processing {avg_ms:.2f} ms exceeds 10 ms budget.\n"
        f"Total: {elapsed:.3f}s for {N} files."
    )
