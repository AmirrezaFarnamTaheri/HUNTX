import asyncio
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from huntx.pipeline.ingest import IngestionPipeline
from huntx.state.db import open_db
from huntx.state.repo import StateRepo
from huntx.store.raw_store import RawStore


@dataclass
class _Item:
    external_id: str
    data: bytes
    metadata: dict


class _AckConnector:
    def __init__(self):
        self.acked: list[str] = []

    def list_new(self, _state):
        return [
            _Item("1", b"one", {"filename": "one.txt"}),
            _Item("2", b"two", {"filename": "two.txt"}),
        ]

    def acknowledge(self, items):
        self.acked.extend(item.external_id for item in items)

    def get_state(self):
        return {"offset": len(self.acked)}


class IngestAcknowledgementTests(unittest.TestCase):
    def test_acknowledges_only_after_batch_is_durable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = _AckConnector()
            db = open_db(root / "state.db")
            pipeline = IngestionPipeline(
                RawStore(root / "raw"),
                StateRepo(db),
            )

            asyncio.run(pipeline.run("source", connector))

            self.assertEqual(connector.acked, ["1", "2"])
            with db.connect() as conn:
                count = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
            self.assertEqual(count, 2)

    def test_failed_batch_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = _AckConnector()
            db = open_db(root / "state.db")
            pipeline = IngestionPipeline(
                RawStore(root / "raw"),
                StateRepo(db),
            )

            def fail_batch(*_args, **_kwargs):
                raise RuntimeError("database unavailable")

            pipeline._process_batch = fail_batch  # type: ignore[method-assign]
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                asyncio.run(pipeline.run("source", connector))

            self.assertEqual(connector.acked, [])


if __name__ == "__main__":
    unittest.main()
