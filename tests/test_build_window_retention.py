"""Build window: user-facing artifacts accumulate the retention window, not one run.

The workflow publishes every two hours. A cutoff of "only this run's new
observations" made each release hold roughly one run of content. The requested
contract is a rolling cumulative window: keep every record whose observation was
ingested within OUTPUT_RETENTION_DAYS (default 3 days = 36 two-hour runs), so
stale entries age out on schedule while failed runs never shrink the release.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from huntx.config.schema import AppConfig
from huntx.core.orchestrator import Orchestrator
from huntx.state.db import open_db


def _empty_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "sources": [],
            "publishing": {"routes": []},
        }
    )


def _window_orchestrator(db_path: Path, retention_days: int = 3) -> Orchestrator:
    orchestrator = object.__new__(Orchestrator)
    orchestrator.db = open_db(db_path)
    orchestrator.OUTPUT_RETENTION_DAYS = retention_days
    return orchestrator


class TestBuildWindowMinSeenId(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "state.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _observe(self, source_id: str, external_id: str, *, age_days: float | None = None) -> int:
        with self.orchestrator.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO seen_files (source_id, external_id, raw_hash, ingested_at) "
                "VALUES (?, ?, ?, COALESCE(?, datetime('now')))",
                (source_id, external_id, f"{external_id}-hash", age_days),
            )
            if age_days is not None:
                conn.execute(
                    "UPDATE seen_files SET ingested_at = datetime('now', ?) WHERE id = ?",
                    (f"-{age_days} days", int(cursor.lastrowid)),
                )
            return int(cursor.lastrowid)

    def test_cutoff_keeps_entire_window_not_just_latest_run(self):
        # Two full runs' worth of observations inside three days, plus one older.
        self.orchestrator = _window_orchestrator(self.db_path)
        self._observe("src", "old", age_days=4.0)
        self._observe("src", "fresh-old", age_days=2.5)
        self._observe("src", "fresh-new")

        cutoff = self.orchestrator._get_build_window_min_seen_id()

        self.assertEqual(cutoff, 1, "cutoff sits one below the window minimum so that row is kept")
        with self.orchestrator.db.connect() as conn:
            rows = conn.execute(
                "SELECT external_id FROM seen_files WHERE id > ? ORDER BY id",
                (cutoff,),
            ).fetchall()
        self.assertEqual([row["external_id"] for row in rows], ["fresh-old", "fresh-new"])

    def test_env_override_shrinks_or_grows_the_window(self):
        self.orchestrator = _window_orchestrator(self.db_path)
        self._observe("src", "two-days-old", age_days=2.0)
        self._observe("src", "five-days-old", age_days=5.0)

        with unittest.mock.patch.dict("os.environ", {"HUNTX_OUTPUT_RETENTION_DAYS": "7"}):
            wide = self.orchestrator._get_build_window_min_seen_id()
        with unittest.mock.patch.dict("os.environ", {"HUNTX_OUTPUT_RETENTION_DAYS": "1"}):
            narrow = self.orchestrator._get_build_window_min_seen_id()

        self.assertEqual(wide, 0, "a 7-day window keeps both observations")
        self.assertEqual(narrow, 0, "a 1-day window keeps only the recent observation")

    def test_empty_window_and_read_failure_fall_back_to_include_all(self):
        self.orchestrator = _window_orchestrator(self.db_path)
        self.assertEqual(self.orchestrator._get_build_window_min_seen_id(), 0)

        self.orchestrator.db = MagicMock()
        self.orchestrator.db.connect.side_effect = RuntimeError("database unavailable")
        self.assertEqual(self.orchestrator._get_build_window_min_seen_id(), 0)

    def test_zero_retention_keeps_only_current_run_behavior(self):
        self.orchestrator = _window_orchestrator(self.db_path)
        self._observe("src", "old", age_days=10.0)
        self._observe("src", "new")

        with unittest.mock.patch.dict("os.environ", {"HUNTX_OUTPUT_RETENTION_DAYS": "0"}):
            cutoff = self.orchestrator._get_build_window_min_seen_id()

        self.assertEqual(cutoff, 1)
        with self.orchestrator.db.connect() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM seen_files WHERE id > ?",
                (cutoff,),
            ).fetchone()
        self.assertEqual(rows["n"], 1, "a 0-day window keeps only the newest observation")


if __name__ == "__main__":
    unittest.main()
