# tests/perf/test_transform_bench.py
"""
Throughput benchmark for TransformPipeline._process_single_file.
Run with: pytest tests/perf/test_transform_bench.py -m perf -v
"""
import pytest
from unittest.mock import MagicMock
from huntx.utils.profiler import wall_clock

SAMPLE_DATA = b"vless://abc@192.0.2.1:443?security=tls&sni=example.com#t\n" * 200
N = 100


@pytest.mark.perf
def test_process