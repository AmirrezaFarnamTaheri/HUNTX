import unittest
import os
from unittest.mock import patch, mock_open
from mergebot.config.env_expand import expand_env
from mergebot.config.loader import load_config

class TestEnvExpand(unittest.TestCase):
    def test_expand_var(self):
        os.environ["TEST_VAR"] = "expanded_value"
        text = "This is ${TEST_VAR}."
        expected = "This is expanded_value."
        self.assertEqual(expand_env(text), expected)
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]

    def test_expand_missing_var(self):
        text = "This is ${MISSING_VAR}."
        expected = "This is ."
        self.assertEqual(expand_env(text), expected)

    def test_no_expand(self):
        text = "No vars here."
        self.assertEqual(expand_env(text), text)

class TestLoader(unittest.TestCase):
    @patch("builtins.open", new_callable=mock_open, read_data="sources: []\npublishing: {}")
    def test_load_empty_config(self, mock_file):
        config = load_config("dummy_path")
        self.assertEqual(len(config.sources), 0)

    @patch("builtins.open", new_callable=mock_open)
    def test_load_config_missing_required_fields(self, mock_file):
        # Case 1: Source missing 'id'
        yaml_content = """
sources:
  - type: telegram
    selector:
      include_formats: ["ovpn"]
"""
        mock_file.return_value.read.return_value = yaml_content
        with self.assertRaises(ValueError) as cm:
            load_config("dummy_path")
        self.assertIn("missing required fields", str(cm.exception))

    @patch("builtins.open", new_callable=mock_open)
    def test_load_config_telegram_missing_token(self, mock_file):
        # Case 2: Telegram source missing token
        yaml_content = """
sources:
  - id: src1
    type: telegram
    selector:
      include_formats: ["ovpn"]
    telegram:
      chat_id: "123"
"""
        mock_file.return_value.read.return_value = yaml_content
        with self.assertRaises(ValueError) as cm:
            load_config("dummy_path")
        self.assertIn("missing 'token' or 'chat_id'", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
