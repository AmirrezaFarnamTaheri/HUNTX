import unittest
from unittest.mock import patch
import os
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

        # Ensure file exists
        self.assertTrue(os.path.exists(config_path), "Config file does not exist")

        # Load config
        config = load_config(config_path)

        # Validate using pydantic
        self.assertIsNotNone(config)

        # Validate sources count (49 sources as of latest config)
        self.assertGreaterEqual(len(config.sources), 49, "Expected at least 49 sources")

        # Validate destinations
        route = next((r for r in config.publishing.routes if r.name == "all_sources"), None)
        self.assertIsNotNone(route, "Route 'all_sources' not found")

        self.assertTrue(len(route.destinations) > 0, "Destinations list is empty")
        dest = route.destinations[0]
        self.assertEqual(dest.chat_id, "8526064109")
        self.assertEqual(dest.mode, "post_on_change")

        # Validate formats count (12 formats)
        self.assertEqual(len(route.formats), 12, "Expected 12 formats in all_sources route")

        # Validate from_sources matches sources count
        self.assertEqual(
            len(route.from_sources), len(config.sources),
            "from_sources count should match total sources count"
        )

        # Validate logic (duplicate IDs etc)
        validate_config(config)


if __name__ == "__main__":
    unittest.main()
