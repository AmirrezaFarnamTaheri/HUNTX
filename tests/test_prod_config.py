import os
import unittest
from unittest.mock import patch

from huntx.config.loader import load_config
from huntx.config.validate import validate_config


class TestProdConfig(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_API_ID": "12345",
            "TELEGRAM_API_HASH": "test_hash",
            "TELEGRAM_USER_SESSION": "test_session",
            "TELEGRAM_TOKEN": "12345:test_token",
        },
    )
    def test_prod_config_validity(self):
        config_path = "configs/config.prod.yaml"

        self.assertTrue(os.path.exists(config_path), "Config file does not exist")
        config = load_config(config_path)
        self.assertIsNotNone(config)
        self.assertGreater(len(config.sources), 0, "Expected at least 1 source")

        route = next((r for r in config.publishing.routes if r.name == "all_sources"), None)
        self.assertIsNotNone(route, "Route 'all_sources' not found")

        # Production had a stale hard-coded Telegram chat that deterministically
        # returned `chat not found`. Publication is now deliberately opt-in:
        # operators add a destination only together with its dedicated
        # PUBLISH_BOT_TOKEN/destination token.
        self.assertEqual(route.destinations, [])

        self.assertGreater(len(route.formats), 0, "Expected at least 1 format in all_sources route")
        self.assertEqual(
            len(route.from_sources),
            len(config.sources),
            "from_sources count should match total sources count",
        )

        validate_config(config)


if __name__ == "__main__":
    unittest.main()
