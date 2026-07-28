"""Unit tests for pydantic field validators in ``huntx.config.schema``.

Focus: the ``api_id`` coercion contract — absent values are optional and map
to ``None``, but a non-empty, non-numeric value is a genuine misconfiguration
and must be rejected rather than silently discarded.
"""

import unittest

from pydantic import ValidationError

from huntx.config.schema import TelegramUserSourceConfig, TelegramSourceConfig


class TestApiIdValidator(unittest.TestCase):
    def test_numeric_string_is_coerced(self):
        cfg = TelegramUserSourceConfig(api_id="12345", peer="@c")
        self.assertEqual(cfg.api_id, 12345)

    def test_integer_is_preserved(self):
        cfg = TelegramUserSourceConfig(api_id=678, peer="@c")
        self.assertEqual(cfg.api_id, 678)

    def test_absent_values_map_to_none(self):
        for absent in (None, "", 0):
            cfg = TelegramUserSourceConfig(api_id=absent, peer="@c")
            self.assertIsNone(cfg.api_id, f"expected None for {absent!r}")

    def test_string_zero_maps_to_none(self):
        # "0" fails the `v == 0` fast-path (str != int in Python) and must be
        # normalized to None *after* parsing, not just before.
        cfg = TelegramUserSourceConfig(api_id="0", peer="@c")
        self.assertIsNone(cfg.api_id)

    def test_omitted_api_id_is_none(self):
        cfg = TelegramUserSourceConfig(peer="@c")
        self.assertIsNone(cfg.api_id)

    def test_garbage_value_is_rejected(self):
        with self.assertRaises(ValidationError):
            TelegramUserSourceConfig(api_id="not_an_int", peer="@c")

    def test_unexpanded_placeholder_is_rejected(self):
        # A leftover ``${...}`` placeholder must not be silently swallowed.
        with self.assertRaises(ValidationError):
            TelegramUserSourceConfig(api_id="${TELEGRAM_API_ID}", peer="@c")


class TestTokenValidator(unittest.TestCase):
    def test_valid_token_preserved(self):
        cfg = TelegramSourceConfig(token="123:ABC", chat_id="-100")
        self.assertEqual(cfg.token, "123:ABC")

    def test_token_without_colon_becomes_none(self):
        cfg = TelegramSourceConfig(token="garbage", chat_id="-100")
        self.assertIsNone(cfg.token)

    def test_empty_token_becomes_none(self):
        cfg = TelegramSourceConfig(token="", chat_id="-100")
        self.assertIsNone(cfg.token)


if __name__ == "__main__":
    unittest.main()
