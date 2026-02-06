import unittest
from unittest.mock import MagicMock, patch
from mergebot.core.orchestrator import Orchestrator
from mergebot.config.schema import AppConfig, SourceConfig, TelegramSourceConfig, TelegramUserSourceConfig, PublishRoute, DestinationConfig, SourceSelector

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig(
            sources=[
                SourceConfig(
                    id="src_bot",
                    type="telegram",
                    selector=SourceSelector(include_formats=["fmt"]),
                    telegram=TelegramSourceConfig(token="bot_token", chat_id="123")
                ),
                SourceConfig(
                    id="src_user",
                    type="telegram_user",
                    selector=SourceSelector(include_formats=["fmt"]),
                    telegram_user=TelegramUserSourceConfig(api_id=1, api_hash="h", session="s", peer="@p")
                ),
                SourceConfig(
                    id="src_skip",
                    type="unknown",
                    selector=SourceSelector(include_formats=["fmt"])
                )
            ],
            routes=[
                PublishRoute(
                    name="route1",
                    from_sources=["src_bot"],
                    formats=["fmt"],
                    destinations=[
                        DestinationConfig(chat_id="dest1", mode="telegram", caption_template="cap")
                    ]
                )
            ]
        )

    @patch('mergebot.core.orchestrator.RawStore')
    @patch('mergebot.core.orchestrator.ArtifactStore')
    @patch('mergebot.core.orchestrator.open_db')
    @patch('mergebot.core.orchestrator.StateRepo')
    @patch('mergebot.core.orchestrator.FormatRegistry')
    @patch('mergebot.core.orchestrator.IngestionPipeline')
    @patch('mergebot.core.orchestrator.TransformPipeline')
    @patch('mergebot.core.orchestrator.BuildPipeline')
    @patch('mergebot.core.orchestrator.PublishPipeline')
    @patch('mergebot.core.orchestrator.TelegramConnector')
    @patch('mergebot.core.orchestrator.TelegramUserConnector')
    def test_run_orchestrator(self, MockUserConn, MockBotConn, MockPub, MockBuild, MockTrans, MockIngest, MockReg, MockRepo, MockOpenDB, MockArtStore, MockRawStore):

        orch = Orchestrator(self.config)

        # Setup mocks
        mock_build_pipeline = MockBuild.return_value
        mock_build_pipeline.run.return_value = ["fake_result"]

        orch.run()

        # Check Ingestion
        self.assertEqual(MockBotConn.call_count, 1) # One bot source
        self.assertEqual(MockUserConn.call_count, 1) # One user source

        # Verify ingest pipeline called for both
        self.assertEqual(MockIngest.return_value.run.call_count, 2)

        # Verify transform
        MockTrans.return_value.process_pending.assert_called_once()

        # Verify build
        mock_build_pipeline.run.assert_called_once()

        # Verify publish
        MockPub.return_value.run.assert_called_once()

    @patch('mergebot.core.orchestrator.RawStore')
    @patch('mergebot.core.orchestrator.ArtifactStore')
    @patch('mergebot.core.orchestrator.open_db')
    @patch('mergebot.core.orchestrator.StateRepo')
    @patch('mergebot.core.orchestrator.FormatRegistry')
    @patch('mergebot.core.orchestrator.IngestionPipeline')
    @patch('mergebot.core.orchestrator.TransformPipeline')
    @patch('mergebot.core.orchestrator.BuildPipeline')
    @patch('mergebot.core.orchestrator.PublishPipeline')
    def test_orchestrator_initialization(self, *args):
        orch = Orchestrator(self.config)
        self.assertIsNotNone(orch)
