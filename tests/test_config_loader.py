import unittest
import os
import tempfile
from pathlib import Path
from mergebot.config.loader import load_config
from mergebot.config.schema import AppConfig

class TestConfigLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.test_dir.name) / "config.yaml"

    def tearDown(self):
        self.test_dir.cleanup()

    def test_load_valid_config(self):
        config_content = """
        sources:
          - id: test_source
            type: telegram
            telegram:
              token: "123:ABC"
              chat_id: "-1001"
            selector:
              include_formats: ["all"]
        publishing:
          routes:
            - name: test_route
              from_sources: ["test_source"]
              formats: ["npvt"]
              destinations:
                - chat_id: "-1002"
                  mode: bundle
        """
        with open(self.config_path, "w") as f:
            f.write(config_content)

        config = load_config(self.config_path)
        self.assertIsInstance(config, AppConfig)
        self.assertEqual(len(config.sources), 1)
        self.assertEqual(config.sources[0].id, "test_source")
        # routes is accessed via property
        self.assertEqual(len(config.routes), 1)
        self.assertEqual(config.routes[0].name, "test_route")

    def test_load_telegram_user_config(self):
        config_content = """
        sources:
          - id: user_source
            type: telegram_user
            telegram_user:
              api_id: 12345
              api_hash: "hash"
              session: "session_str"
              peer: "@channel"
            selector:
              include_formats: ["all"]
        publishing:
          routes: []
        """
        with open(self.config_path, "w") as f:
            f.write(config_content)

        config = load_config(self.config_path)
        self.assertEqual(len(config.sources), 1)
        src = config.sources[0]
        self.assertEqual(src.type, "telegram_user")
        self.assertIsNotNone(src.telegram_user)
        self.assertEqual(src.telegram_user.api_id, 12345)
        self.assertEqual(src.telegram_user.peer, "@channel")

    def test_load_telegram_user_config_invalid_api_id(self):
        config_content = """
        sources:
          - id: user_source
            type: telegram_user
            telegram_user:
              api_id: "not_an_int"
              api_hash: "hash"
              session: "session_str"
              peer: "@channel"
            selector:
              include_formats: ["all"]
        publishing:
          routes: []
        """
        with open(self.config_path, "w") as f:
            f.write(config_content)

        # Should fail validation now (Pydantic is strict)
        with self.assertRaises(Exception):
            load_config(self.config_path)

    def test_load_telegram_user_config_missing_fields(self):
        config_content = """
        sources:
          - id: user_source
            type: telegram_user
            telegram_user:
              api_id: 12345
              # Missing hash
            selector:
              include_formats: ["all"]
        publishing:
          routes: []
        """
        with open(self.config_path, "w") as f:
            f.write(config_content)

        # Should fail
        with self.assertRaises(Exception):
            load_config(self.config_path)

    def test_load_invalid_yaml(self):
        with open(self.config_path, "w") as f:
            f.write("invalid: yaml: [")

        with self.assertRaises(Exception):
            load_config(self.config_path)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_config(Path("non_existent.yaml"))

if __name__ == '__main__':
    unittest.main()
