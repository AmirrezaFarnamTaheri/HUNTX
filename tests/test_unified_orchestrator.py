import unittest
from unittest.mock import MagicMock, patch

from huntx.core.unified_orchestrator import UnifiedOrchestrator
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


class TestUnifiedOrchestrator(unittest.TestCase):

    def setUp(self):
        self.config = AppConfig(
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
    @patch("huntx.connectors.telegram.connector.TelegramConnector")
    @patch("huntx.connectors.telegram_user.connector.TelegramUserConnector")
    def test_unified_orchestrator_run(
        self,
        mock_user_conn,
        mock_bot_conn,
        mock_pub,
        mock_build,
        mock_trans,
        mock_ingest,
        mock_reg,
        mock_repo,
        mock_open_db,
        mock_art_store,
        mock_raw_store,
    ):
        orch = UnifiedOrchestrator(self.config, enable_benchmarking=True)
        res = orch.run(no_publish=True)

        assert res["status"] == "completed"
        assert res["unified"] is True
        assert "elapsed_seconds" in res
