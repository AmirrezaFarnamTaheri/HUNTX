import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from huntx.store import paths as paths_mod
from huntx.core.orchestrator import Orchestrator
from huntx.config.schema import (
    AppConfig,
    SourceConfig,
    TelegramSourceConfig,
    TelegramUserSourceConfig,
    PublishRoute,
    DestinationConfig,
    SourceSelector,
    PublishingConfig,
)


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig(
            sources=[
                SourceConfig(
                    id="src_bot",
                    type="telegram",
                    selector=SourceSelector(include_formats=["fmt"]),
                    telegram=TelegramSourceConfig(token="123:bot_token", chat_id="123"),
                ),
                SourceConfig(
                    id="src_user",
                    type="telegram_user",
                    selector=SourceSelector(include_formats=["fmt"]),
                    telegram_user=TelegramUserSourceConfig(api_id=1, api_hash="h", session="s", peer="@p"),
                ),
                # Removed 'src_skip' because Pydantic would reject 'type="unknown"' due to validator
            ],
            publishing=PublishingConfig(
                routes=[
                    PublishRoute(
                        name="route1",
                        from_sources=["src_bot"],
                        formats=["fmt"],
                        destinations=[DestinationConfig(chat_id="dest1", mode="telegram", caption_template="cap")],
                    )
                ]
            ),
        )

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    # Use sys.modules patching or patch where the class is defined because import is local
    @patch("huntx.connectors.telegram.connector.TelegramConnector")
    @patch("huntx.connectors.telegram_user.connector.TelegramUserConnector")
    def test_run_orchestrator(
        self,
        MockUserConn,
        MockBotConn,
        MockPub,
        MockBuild,
        MockTrans,
        MockIngest,
        MockReg,
        MockRepo,
        MockOpenDB,
        MockArtStore,
        MockRawStore,
    ):

        orch = Orchestrator(self.config)

        # Setup mocks
        mock_build_pipeline = MockBuild.return_value
        mock_build_pipeline.run.return_value = [
            {
                "route_name": "route1",
                "format": "fmt",
                "unique_id": "route1:fmt",
                "artifact_hash": "a" * 64,
                "data": b"artifact",
                "count": 1,
            }
        ]

        orch.run()

        # Check Ingestion
        self.assertEqual(MockBotConn.call_count, 1)  # One bot source
        self.assertEqual(MockUserConn.call_count, 1)  # One user source

        # Verify ingest pipeline called for both
        self.assertEqual(MockIngest.return_value.run.call_count, 2)

        # Verify transform
        MockTrans.return_value.process_pending.assert_called_once()

        # Verify build
        mock_build_pipeline.run.assert_called_once()

        # Verify publish
        MockPub.return_value.run.assert_called_once()

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_orchestrator_initialization(self, *args):
        orch = Orchestrator(self.config)
        self.assertIsNotNone(orch)


class TestOutputRetention(unittest.TestCase):
    """outputs/ must keep cumulative/cached artifacts for >= OUTPUT_RETENTION_DAYS."""

    def _make_config(self):
        return AppConfig(
            sources=[
                SourceConfig(
                    id="src_bot",
                    type="telegram",
                    selector=SourceSelector(include_formats=["fmt"]),
                    telegram=TelegramSourceConfig(token="123:bot_token", chat_id="123"),
                ),
            ],
            publishing=PublishingConfig(
                routes=[
                    PublishRoute(
                        name="route1",
                        from_sources=["src_bot"],
                        formats=["fmt"],
                        destinations=[DestinationConfig(chat_id="dest1", mode="telegram", caption_template="cap")],
                    )
                ]
            ),
        )

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_recent_stale_retained_old_stale_pruned(self, *args):
        orch = Orchestrator(self._make_config())
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "outputs"
            out_dir.mkdir()
            # Rebind the orchestrator's paths to the temp output dir.
            orch.paths = paths_mod.RuntimePaths(
                data_dir=Path(tmp),
                raw_store_dir=Path(tmp),
                artifact_store_dir=Path(tmp),
                rejects_dir=Path(tmp),
                state_dir=Path(tmp),
                logs_dir=Path(tmp),
                output_dir=out_dir,
                dev_output_dir=Path(tmp) / "dev",
                state_db_path=Path(tmp) / "state.db",
            )

            # A route-owned file produced long ago (older than retention window).
            old_file = out_dir / "route1.old"
            old_file.write_text("old", encoding="utf-8")
            old_mtime = time.time() - (orch.OUTPUT_RETENTION_DAYS + 1) * 86400
            os.utime(old_file, (old_mtime, old_mtime))

            # A route-owned file produced recently (within retention window).
            recent_file = out_dir / "route1.recent"
            recent_file.write_text("recent", encoding="utf-8")

            # A non-pipeline helper file must always be preserved.
            helper = out_dir / "README.md"
            helper.write_text("keep me", encoding="utf-8")

            # Current run produces one fresh artifact for route1.
            results = [{"route_name": "route1", "format": "fmt", "data": b"new"}]
            orch._export_outputs(results)

            # New artifact written.
            self.assertTrue((out_dir / orch._output_filename("route1", "fmt")).exists())
            # Old stale route file pruned.
            self.assertFalse(old_file.exists())
            # Recent stale route file retained (cumulative cache within window).
            self.assertTrue(recent_file.exists())
            # Non-pipeline helper preserved.
            self.assertTrue(helper.exists())

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_env_var_overrides_retention_window(self, *args):
        orch = Orchestrator(self._make_config())
        old_env = os.environ.get("HUNTX_OUTPUT_RETENTION_DAYS")
        try:
            os.environ["HUNTX_OUTPUT_RETENTION_DAYS"] = "0"
            self.assertEqual(orch._output_retention_days(), 0)
            os.environ["HUNTX_OUTPUT_RETENTION_DAYS"] = "14"
            self.assertEqual(orch._output_retention_days(), 14)
            os.environ["HUNTX_OUTPUT_RETENTION_DAYS"] = "not-a-number"
            self.assertEqual(orch._output_retention_days(), orch.OUTPUT_RETENTION_DAYS)
            del os.environ["HUNTX_OUTPUT_RETENTION_DAYS"]
            self.assertEqual(orch._output_retention_days(), orch.OUTPUT_RETENTION_DAYS)
        finally:
            if old_env is None:
                os.environ.pop("HUNTX_OUTPUT_RETENTION_DAYS", None)
            else:
                os.environ["HUNTX_OUTPUT_RETENTION_DAYS"] = old_env
