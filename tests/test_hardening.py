import unittest
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from huntx.config.schema import (
    AppConfig,
    SourceConfig,
    PublishingConfig,
    PublishRoute,
    DestinationConfig,
    TelegramSourceConfig,
    TelegramUserSourceConfig,
)
from huntx.config.validate import validate_config
from huntx.store.artifact_store import ArtifactStore
from huntx.pipeline.publish import PublishPipeline
from huntx.state.repo import StateRepo


class TestHardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = ArtifactStore(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. PATH TRAVERSAL TESTS
    @patch("huntx.store.artifact_store.safe_component")
    def test_artifact_store_save_artifact_traversal_route(self, mock_safe):
        # safe_component is mocked to return traversal segment
        mock_safe.return_value = "../../../../traversal"
        with self.assertRaises(ValueError) as ctx:
            self.store.save_artifact("any", "fmt", b"data")
        self.assertIn("traversal", str(ctx.exception).lower())

    @patch("huntx.store.artifact_store.safe_component")
    def test_artifact_store_save_artifact_traversal_format(self, mock_safe):
        # We let the route name pass but make format traversal
        mock_safe.side_effect = lambda x, **kwargs: "ok_route" if x == "any" else "../../../../traversal"
        with self.assertRaises(ValueError) as ctx:
            self.store.save_artifact("any", "fmt", b"data")
        self.assertIn("traversal", str(ctx.exception).lower())

    @patch("huntx.store.artifact_store.safe_component")
    def test_artifact_store_save_output_traversal(self, mock_safe):
        mock_safe.return_value = "../../../../traversal"
        with self.assertRaises(ValueError) as ctx:
            self.store.save_output("any", "fmt", b"data")
        self.assertIn("traversal", str(ctx.exception).lower())

    @patch("huntx.store.artifact_store.safe_component")
    def test_artifact_store_save_to_archive_traversal(self, mock_safe):
        mock_safe.return_value = "../../../../traversal"
        with self.assertRaises(ValueError) as ctx:
            self.store.save_to_archive("any", "fmt", b"data")
        self.assertIn("traversal", str(ctx.exception).lower())

    # 2. CONFIG VALIDATION TESTS
    def test_validate_config_duplicate_source_id(self):
        src1 = SourceConfig(id="s1", type="telegram", telegram=TelegramSourceConfig(token="123:abc", chat_id="11"))
        src2 = SourceConfig(id="s1", type="telegram", telegram=TelegramSourceConfig(token="456:def", chat_id="22"))
        config = AppConfig(sources=[src1, src2], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("duplicate source id", str(ctx.exception).lower())

    def test_validate_config_unexpanded_source_id(self):
        src = SourceConfig(id="${SRC_ID}", type="telegram", telegram=TelegramSourceConfig(token="123:abc", chat_id="11"))
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("invalid/unexpanded id", str(ctx.exception).lower())

    def test_validate_config_telegram_missing_block(self):
        src = SourceConfig(id="s1", type="telegram", telegram=None)
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("missing 'telegram' block", str(ctx.exception).lower())

    def test_validate_config_telegram_forbidden_user_block(self):
        src = SourceConfig(
            id="s1",
            type="telegram",
            telegram=TelegramSourceConfig(token="123:abc", chat_id="11"),
            telegram_user=TelegramUserSourceConfig(api_id=123, api_hash="hash", session="s", peer="p")
        )
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("forbidden 'telegram_user' block", str(ctx.exception).lower())

    def test_validate_config_telegram_user_missing_block(self):
        src = SourceConfig(id="s1", type="telegram_user", telegram_user=None)
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("missing 'telegram_user' block", str(ctx.exception).lower())

    def test_validate_config_telegram_user_forbidden_telegram_block(self):
        src = SourceConfig(
            id="s1",
            type="telegram_user",
            telegram=TelegramSourceConfig(token="123:abc", chat_id="11"),
            telegram_user=TelegramUserSourceConfig(api_id=123, api_hash="hash", session="s", peer="p")
        )
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("forbidden 'telegram' block", str(ctx.exception).lower())

    def test_validate_config_unrecognized_route_format(self):
        src = SourceConfig(id="s1", type="telegram", telegram=TelegramSourceConfig(token="123:abc", chat_id="11"))
        route = PublishRoute(
            name="r1",
            from_sources=["s1"],
            formats=["invalid_format_xyz"],
            destinations=[]
        )
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[route]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("unrecognized format id", str(ctx.exception).lower())

    @patch.dict(os.environ, {"HUNTX_STRICT": "1"})
    def test_validate_config_strict_mode_missing_dest_token(self):
        src = SourceConfig(id="s1", type="telegram", telegram=TelegramSourceConfig(token="123:abc", chat_id="11"))
        route = PublishRoute(
            name="r1",
            from_sources=["s1"],
            formats=["npvt"],
            destinations=[DestinationConfig(chat_id="123", mode="telegram", token=None)]
        )
        config = AppConfig(sources=[src], publishing=PublishingConfig(routes=[route]))
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("missing/unexpanded token in strict mode", str(ctx.exception).lower())

    # 3. PUBLISH PIPELINE STRICT MODE
    @patch.dict(os.environ, {"HUNTX_STRICT": "1"})
    def test_publish_pipeline_strict_missing_token(self):
        mock_repo = MagicMock(spec=StateRepo)
        mock_repo.get_last_published_hash.return_value = None
        pipeline = PublishPipeline(mock_repo)

        build_result = {
            "route_name": "r1",
            "artifact_hash": "hash123",
            "format": "npvt",
            "data": b"test_data",
        }
        destinations = [
            {"chat_id": "123", "mode": "telegram", "token": ""}
        ]

        with self.assertRaises(RuntimeError) as ctx:
            pipeline.run(build_result, destinations)
        self.assertIn("strict mode active: no token configured", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
