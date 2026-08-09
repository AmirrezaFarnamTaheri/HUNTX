# tests/perf/test_ingest_bench.py
"""
Throughput benchmark for IngestionPipeline._process_batch.
Run with: pytest tests/perf/ -m perf -v
"""
import pytest
from unittest.mock import MagicMock
from huntx.utils.profiler import wall_clock

ITEM_COUNT = 100
ITEM_DATA = b"vless://abc@192.0.2.1:443?security=tls#t\n" * 10  # ~420 bytes


def _make_item(i: int):
    item = MagicMock()
    item.external_id = f"ext_{i}"
    item.data = ITEM_DATA
    item.metadata = {"filename": f"file_{i}.txt", "is_text": True}
    return item


@pytest.mark.perf
def test_process_batch_under_200ms():
    """100 new items must batch-process in < 200 ms."""
    from huntx.pipeline.ingest import IngestionPipeline

    raw_store = MagicMock()
    raw_store.save.side_effect = lambda data: "a" * 64

    conn = MagicMock()
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)

    state_repo = MagicMock()
    state_repo.get_seen_files_batch.return_value = set()
    state_repo.record_files_batch.return_value = None
    state_repo.db.connect.return_value = conn

    pipeline = IngestionPipeline(raw_store, state_repo)
    items = [_make_item(i) for i in range(ITEM_COUNT)]

    _, elapsed = wall_clock(pipeline._process_batch, "source_1", items, conn)

    assert elapsed < 0.2, (
        f"_process_batch({ITEM_COUNT} items) took {elapsed:.3f}s — "
        f"exceeds 200 ms budget."
    )
