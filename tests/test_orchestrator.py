import unittest
from unittest.mock import patch
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
        mock_build_pipeline.run.return_value = ["fake_result"]

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
